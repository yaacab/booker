"""Release transaction harness with fake services and no SSH or production paths."""

import fcntl
import importlib.util
import json
import os
import subprocess
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[3]
OLD = "20261001T000000Z-aaaaaaaaaaaa"
NEW = "20261002T000000Z-bbbbbbbbbbbb"


def _module():
    spec = importlib.util.spec_from_file_location("booker_release_deploy", ROOT / "infra/release_deploy.py")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _release(root: Path, release_id: str):
    release = root / "releases" / release_id
    for directory in (
        "apps/api/booker_api", "apps/api/alembic/versions", "apps/web",
        "infra/systemd", "infra/nginx", "scripts",
    ):
        (release / directory).mkdir(parents=True, exist_ok=True)
    for name, content in {
        "apps/api/booker_api/models.py": "schema = 1\n",
        "apps/api/booker_api/db.py": "migration = 1\n",
        "apps/api/alembic/versions/rev.py": "revision = 'rev'\n",
        "apps/api/requirements-prod.lock": "fastapi==1.0\n",
        "apps/web/package-lock.json": '{"lockfileVersion":3}',
        "infra/systemd/booker-api.service": "ExecStart=/opt/booker/current/.venv/bin/uvicorn --no-proxy-headers --no-access-log\n",
        "infra/systemd/booker-web.service": "ExecStart=/opt/booker/current/apps/web/node_modules/.bin/next\n",
        "infra/nginx/bukergo.ru.conf": "include /opt/booker/current/infra/nginx/booker-https-headers.conf;\n",
        "infra/nginx/booker-https-headers.conf": "include /opt/booker/current/infra/nginx/booker-common-headers.conf;\n",
        "infra/nginx/booker-common-headers.conf": "add_header X-Test test always;\n",
        "infra/cron-booker-backup.example": "* * * * * root /opt/booker/current/infra/run-booker-ops-backup.sh\n",
    }.items():
        (release / name).write_text(content, encoding="utf-8")
    return release


class FakeRunner:
    def __init__(self, root: Path, fail: str | None = None):
        self.root = root
        self.fail = fail
        self.calls = []
        self.failed = False

    def __call__(self, args, *, cwd=None, env=None):
        self.calls.append((tuple(args), cwd))
        current = self.root / "current"
        active = os.readlink(current).split("/")[-1] if current.is_symlink() else None
        action = None
        if args[:3] == ["python3", "-m", "venv"]:
            Path(args[3], "bin").mkdir(parents=True)
        if args[:3] == ["npm", "run", "build"]:
            action = "prebuild"
            output = Path(cwd) / ".next"
            output.mkdir()
            (output / "BUILD_ID").write_text("new-build", encoding="utf-8")
        if args[:2] == ["nginx", "-s"] and active == NEW:
            action = "nginx_reload"
        if args[0] == "curl" and active == NEW and "/internal/readiness" in args[-1]:
            action = "api_probe"
        if args[0] == "curl" and active == NEW and ":3030/" in args[-1]:
            action = "web_probe"
        if args[0] == "curl" and active == OLD and "/internal/readiness" in args[-1]:
            action = "rollback_health"
        if action is not None and self.fail == action and (not self.failed or action == "rollback_health"):
            self.failed = True
            raise subprocess.CalledProcessError(1, args)


@pytest.fixture()
def harness(tmp_path):
    root = tmp_path / "booker"
    (root / "releases").mkdir(parents=True)
    (root / "data/uploads").mkdir(parents=True)
    old = _release(root, OLD)
    new = _release(root, NEW)
    (old / ".venv/bin").mkdir(parents=True)
    (old / ".venv/bin/python").write_text("old-python", encoding="utf-8")
    (old / "apps/web/node_modules").mkdir()
    (old / "apps/web/node_modules/marker").write_text("old-modules", encoding="utf-8")
    (old / "apps/web/.next").mkdir()
    (old / "apps/web/.next/BUILD_ID").write_text("old-build", encoding="utf-8")
    (root / "current").symlink_to(f"releases/{OLD}")
    etc = tmp_path / "etc"
    systemd = etc / "systemd"
    nginx = etc / "nginx"
    enabled = etc / "enabled"
    cron = etc / "cron"
    for path in (systemd, nginx, enabled, cron):
        path.mkdir(parents=True)
    (systemd / "booker-api.service").write_text("old-api-unit", encoding="utf-8")
    (systemd / "booker-web.service").write_text("old-web-unit", encoding="utf-8")
    (nginx / "bukergo.ru.conf").write_text("old-nginx", encoding="utf-8")
    (enabled / "bukergo.ru.conf").symlink_to(nginx / "bukergo.ru.conf")
    (cron / "booker-backup").write_text("old-cron", encoding="utf-8")
    env_file = etc / "booker-api.env"
    env_file.write_text("BOOKER_DATABASE_URL=sqlite:////opt/booker/data/booker.db\n")
    env_file.chmod(0o600)

    def deployer(fail=None):
        module = _module()
        runner = FakeRunner(root, fail)
        release = module.ReleaseDeployer(
            root, NEW, systemd_dir=systemd, nginx_dir=nginx,
            enabled_dir=enabled, cron_dir=cron, env_file=env_file, runner=runner,
        )
        return module, release, runner

    return root, old, new, deployer


def _old_untouched(old):
    assert (old / ".venv/bin/python").read_text() == "old-python"
    assert (old / "apps/web/node_modules/marker").read_text() == "old-modules"
    assert (old / "apps/web/.next/BUILD_ID").read_text() == "old-build"


def test_success_switches_once_and_keeps_previous_unchanged(harness):
    root, old, new, factory = harness
    _module_value, deployer, runner = factory()
    deployer.run()
    assert os.readlink(root / "current") == f"releases/{NEW}"
    evidence = json.loads((new / "release-evidence.json").read_text())
    assert evidence["previous_release"] == OLD
    assert set(evidence["artifacts_sha256"]) == set(_module().ARTIFACT_FILES)
    assert (new / "release-evidence.json").stat().st_mode & 0o777 == 0o600
    assert any(args[:2] == ("nginx", "-t") for args, _ in runner.calls)
    assert not (root / "shared/deploy-state.json").exists()
    _old_untouched(old)


@pytest.mark.parametrize("failure", ["prebuild", "api_probe", "web_probe", "nginx_reload"])
def test_failures_leave_or_restore_previous(harness, failure):
    root, old, _new, factory = harness
    module, deployer, _runner = factory(failure)
    with pytest.raises(module.ReleaseError):
        deployer.run()
    assert os.readlink(root / "current") == f"releases/{OLD}"
    assert (deployer.configs["api"]).read_text() == "old-api-unit"
    assert (deployer.configs["nginx"]).read_text() == "old-nginx"
    assert (deployer.configs["cron"]).read_text() == "old-cron"
    assert not (root / "shared/deploy-state.json").exists()
    _old_untouched(old)


def test_rollback_health_failure_is_critical_and_keeps_state(harness):
    root, old, _new, factory = harness
    module, deployer, runner = factory("api_probe")
    original = runner.__call__

    def fail_both(args, *, cwd=None, env=None):
        if args[0] == "curl" and ("/internal/readiness" in args[-1]) and (
            os.readlink(root / "current") == f"releases/{OLD}"
        ):
            raise subprocess.CalledProcessError(1, args)
        return original(args, cwd=cwd, env=env)

    deployer.runner = fail_both
    with pytest.raises(module.ReleaseError, match="CRITICAL"):
        deployer.run()
    assert os.readlink(root / "current") == f"releases/{OLD}"
    assert json.loads((root / "shared/deploy-state.json").read_text())["phase"] == "rollback_failed"
    _old_untouched(old)


def test_first_deploy_can_switch_and_failed_first_switch_removes_current(harness):
    root, _old, _new, factory = harness
    (root / "current").unlink()
    for path in (root.parent / "etc/systemd").glob("booker-*.service"):
        path.unlink()
    for path in (root.parent / "etc/nginx").glob("bukergo.ru.conf"):
        path.unlink()
    (root.parent / "etc/enabled/bukergo.ru.conf").unlink()
    (root.parent / "etc/cron/booker-backup").unlink()
    module, failing, _runner = factory("web_probe")
    with pytest.raises(module.ReleaseError):
        failing.run()
    assert not (root / "current").exists()
    # A fresh release ID is required after a failed attempt; the old staged tree is retained.
    fresh = "20261002T010000Z-cccccccccccc"
    candidate = _release(root, fresh)
    good = module.ReleaseDeployer(
        root, fresh, systemd_dir=failing.systemd_dir, nginx_dir=failing.nginx_dir,
        enabled_dir=failing.enabled_dir, cron_dir=failing.configs["cron"].parent,
        env_file=failing.env_file, runner=FakeRunner(root),
    )
    good.run()
    assert os.readlink(root / "current") == f"releases/{fresh}"
    assert (candidate / "release-evidence.json").is_file()


def test_schema_change_fails_before_build(harness):
    root, old, new, factory = harness
    (new / "apps/api/booker_api/models.py").write_text("schema = 2\n")
    module, deployer, runner = factory()
    with pytest.raises(module.ReleaseError, match="schema or migration"):
        deployer.run()
    assert os.readlink(root / "current") == f"releases/{OLD}"
    assert runner.calls == []
    _old_untouched(old)


def test_postgres_active_db_cannot_use_stale_sqlite_revision(harness):
    root, _old, new, factory = harness
    (new / "apps/api/booker_api/models.py").write_text("schema = 2\n")
    _module, deployer, runner = factory()
    deployer.env_file.write_text(
        "BOOKER_DATABASE_URL=postgresql+psycopg://localhost/booker\n"
        + "\n".join(f"BOOKER_SCHEMA_{key}={'a' * 64}" for key in (
            "MANIFEST_SHA256", "MIGRATION_EVIDENCE_SHA256", "REHEARSAL_SHA256",
            "BACKUP_SHA256", "SOURCE_REVISION",
        )) + "\n"
    )
    (root / "data/booker.db").write_bytes(b"stale sqlite")
    with pytest.raises(_module.ReleaseError, match="PostgreSQL gate unavailable"):
        deployer.run()
    assert runner.calls == []
    assert os.readlink(root / "current") == f"releases/{OLD}"


def test_invalid_release_and_symlinked_release_rejected(harness, tmp_path):
    root, _old, _new, factory = harness
    module, _deployer, _runner = factory()
    with pytest.raises(module.ReleaseError):
        module.ReleaseDeployer(root, "../../data")
    outside = tmp_path / "outside"
    outside.mkdir()
    evil = "20261002T020000Z-dddddddddddd"
    (root / "releases" / evil).symlink_to(outside, target_is_directory=True)
    with pytest.raises(module.ReleaseError):
        module.ReleaseDeployer(root, evil, env_file=root.parent / "etc/booker-api.env").run()
    assert outside.is_dir()


def test_lock_prevents_parallel_run(harness):
    root, _old, _new, factory = harness
    root.joinpath("shared").mkdir()
    handle = os.open(root / "shared/.deploy.lock", os.O_CREAT | os.O_RDWR, 0o600)
    fcntl.flock(handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
    try:
        _module_value, deployer, _runner = factory()
        with pytest.raises(BlockingIOError):
            deployer.run()
        assert os.readlink(root / "current") == f"releases/{OLD}"
    finally:
        fcntl.flock(handle, fcntl.LOCK_UN)
        os.close(handle)


def test_cleanup_retains_current_previous_and_three_history(harness):
    root, old, _new, factory = harness
    for index in range(5):
        release_id = f"2026090{index + 1}T000000Z-{index + 1:012x}"
        path = _release(root, release_id)
        (path / "release-evidence.json").write_text("{}")
        os.utime(path, (1000 + index, 1000 + index))
    stale = _release(root, "20260801T000000Z-eeeeeeeeeeee")
    os.utime(stale, (1000, 1000))
    recent = _release(root, "20261002T030000Z-ffffffffffff")
    _module_value, deployer, _runner = factory()
    deployer.run()
    history = [path for path in (root / "releases").iterdir()
               if (path / "release-evidence.json").exists() and path.name not in {OLD, NEW}]
    assert len(history) == 3
    assert not stale.exists()
    assert recent.exists()
    _old_untouched(old)


def test_cleanup_failure_cannot_roll_back_committed_release(harness, monkeypatch):
    root, old, new, factory = harness
    _module, deployer, _runner = factory()

    def fail_cleanup(_previous):
        raise OSError("synthetic cleanup failure")

    monkeypatch.setattr(deployer, "_cleanup", fail_cleanup)
    deployer.run()
    assert os.readlink(root / "current") == f"releases/{NEW}"
    assert (new / "release-evidence.json").is_file()
    assert not (root / "shared/deploy-state.json").exists()
    _old_untouched(old)


def test_interrupted_committed_state_does_not_roll_back(harness):
    root, old, new, factory = harness
    module, deployer, _runner = factory()
    deployer.run()
    # Simulate a crash after the durable commit marker but before state cleanup.
    state = {"version": 1, "phase": "committed", "release_id": NEW,
             "previous": OLD, "snapshot": str(root / "shared/deploy-snapshots" / NEW)}
    (root / "shared/deploy-state.json").write_text(json.dumps(state))
    future = "20261002T040000Z-111111111111"
    _release(root, future)
    next_deployer = module.ReleaseDeployer(
        root, future, systemd_dir=deployer.systemd_dir, nginx_dir=deployer.nginx_dir,
        enabled_dir=deployer.enabled_dir, cron_dir=deployer.configs["cron"].parent,
        env_file=deployer.env_file, runner=FakeRunner(root),
    )
    next_deployer.run()
    assert os.readlink(root / "current") == f"releases/{future}"
    assert (new / "release-evidence.json").is_file()
    _old_untouched(old)
