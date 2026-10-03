"""Synthetic canaries prove the scanner fails closed without echoing values."""

import importlib.util
import os
import shutil
import subprocess
import sys
from pathlib import Path

import pytest

from booker_api.config import settings

ROOT = Path(__file__).resolve().parents[3]
SPEC = importlib.util.spec_from_file_location(
    "booker_secret_scan", ROOT / "scripts" / "check_secret_exposure.py"
)
assert SPEC and SPEC.loader
scanner = importlib.util.module_from_spec(SPEC)
sys.modules[SPEC.name] = scanner
SPEC.loader.exec_module(scanner)


def test_provider_token_and_configured_canary_are_reported_without_value():
    token = "ghp_" + "Z" * 30
    canary = "booker_canary_" + "Q7mA8nB9cD2fG3hJ4kL5"
    content = f"log: {token}\nartifact: {canary}\n"
    findings = scanner.scan_text("logs/synthetic.log", content, env_values=(canary,))
    assert {finding.rule for finding in findings} == {"provider-token", "configured-secret"}
    assert all(token not in repr(finding) and canary not in repr(finding) for finding in findings)


def test_database_url_password_detected_in_source_and_server_build(tmp_path):
    password = "M7qR9tY2pL6vB4nK"
    database_url = f"postgresql+psycopg://booker:{password}@db.example/booker"
    source = scanner.scan_text("config.txt", f"BOOKER_DATABASE_URL={database_url}\n")
    assert any(finding.rule == "database-url-credential" for finding in source)
    env_file = tmp_path / "booker-api.env"
    env_file.write_text(f"BOOKER_DATABASE_URL={database_url}\n", encoding="utf-8")
    values = scanner.env_file_values(env_file)
    assert password in values
    build = tmp_path / "apps/web/.next"
    (build / "server").mkdir(parents=True)
    (build / "BUILD_ID").write_text("synthetic", encoding="utf-8")
    (build / "server" / "app.js").write_text(f"const leaked='{password}'", encoding="utf-8")
    findings = scanner.run(root=tmp_path, source=False, build=True, artifacts=[], extra_values=values)
    assert any(finding.rule == "configured-secret" for finding in findings)
    assert password not in repr(findings)
    short_url = "postgresql://booker:q7R@db.example/booker"
    short = scanner.scan_text("config.txt", short_url)
    assert short[0].rule == "database-url-credential"
    literal_pass = scanner.scan_text("config.txt", "postgresql://booker:pass@db.example/booker")
    assert literal_pass[0].rule == "database-url-credential"
    template_url = scanner.scan_text("example.txt", "postgresql://USER:PASS@HOST:5432/booker")
    assert template_url == []
    (build / "server" / "short.js").write_text("const password='q7R'", encoding="utf-8")
    short_findings = scanner.run(
        root=tmp_path, source=False, build=True, artifacts=[], extra_values=("q7R",)
    )
    assert any(finding.rule == "configured-short-secret" for finding in short_findings)


def test_allowlist_is_bound_to_exact_fake_fixture_path():
    fixture = (ROOT / "apps/api/tests/test_support_security.py").read_text(encoding="utf-8")
    token = scanner.TOKEN.search(fixture)
    assert token is not None
    assert scanner.scan_text("apps/api/tests/test_support_security.py", token.group()) == []
    assert scanner.scan_text("apps/api/booker_api/leaked.py", token.group())[0].rule == "provider-token"


def test_source_inventory_includes_tracked_and_untracked_but_excludes_outputs(tmp_path):
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    (tmp_path / "tracked.py").write_text("safe", encoding="utf-8")
    subprocess.run(["git", "add", "tracked.py"], cwd=tmp_path, check=True)
    (tmp_path / "untracked.py").write_text("safe", encoding="utf-8")
    for folder in ("outputs/other-worktree", "apps/web/node_modules", "data/uploads"):
        target = tmp_path / folder
        target.mkdir(parents=True)
        (target / "private.txt").write_text("synthetic", encoding="utf-8")
    names = {path.relative_to(tmp_path).as_posix() for path in scanner.source_paths(tmp_path)}
    assert names == {"tracked.py", "untracked.py"}


def test_deploy_payload_excludes_ignored_env_and_worktree_outputs(tmp_path):
    if not shutil.which("rsync"):
        pytest.skip("rsync unavailable")
    exclusions = tmp_path / "infra/rsync-booker-excludes.txt"
    exclusions.parent.mkdir(parents=True)
    exclusions.write_bytes((ROOT / "infra/rsync-booker-excludes.txt").read_bytes())
    (tmp_path / "safe.py").write_text("print('safe')", encoding="utf-8")
    for name in (".env.local", "outputs/other-worktree/private.py", "apps/api/.ruff_cache/cache"):
        path = tmp_path / name
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text("synthetic", encoding="utf-8")
    paths, issues = scanner.deploy_paths(tmp_path)
    assert issues == []
    names = {path.relative_to(tmp_path).as_posix() for path in paths}
    assert "safe.py" in names
    assert ".env.local" not in names
    assert "outputs/other-worktree/private.py" not in names
    assert "apps/api/.ruff_cache/cache" not in names


def test_build_and_artifact_scan_detects_canary_without_user_uploads(tmp_path, monkeypatch):
    monkeypatch.setenv("BOOKER_WEBHOOK_SECRET", "booker_canary_" + "x9Q8r7S6t5U4v3W2")
    assert scanner.run(root=tmp_path, source=False, build=True, artifacts=[])[0].rule == "build-missing"
    build = tmp_path / "apps/web/.next"
    (build / "static").mkdir(parents=True)
    (build / "BUILD_ID").write_text("synthetic", encoding="utf-8")
    (build / "static" / "chunk.js").write_text(
        "const value='booker_canary_x9Q8r7S6t5U4v3W2'", encoding="utf-8"
    )
    findings = scanner.run(root=tmp_path, source=False, build=True, artifacts=[])
    assert any(finding.rule == "configured-secret" for finding in findings)
    (build / "static" / "public.png").write_bytes(
        b"\x89PNG\x00" + b"booker_canary_x9Q8r7S6t5U4v3W2"
    )
    binary_findings = scanner.run(root=tmp_path, source=False, build=True, artifacts=[])
    assert any(finding.rule == "configured-secret-binary" for finding in binary_findings)
    upload = tmp_path / "data/uploads/user.txt"
    upload.parent.mkdir(parents=True)
    upload.write_text("booker_canary_x9Q8r7S6t5U4v3W2", encoding="utf-8")
    rejected = scanner.run(root=tmp_path, source=False, build=False, artifacts=[upload])
    assert rejected[0].rule == "artifact-path-not-approved"
    log = tmp_path / "logs/test.log"
    log.parent.mkdir(parents=True)
    log.write_text("booker_canary_x9Q8r7S6t5U4v3W2", encoding="utf-8")
    logged = scanner.run(root=tmp_path, source=False, build=False, artifacts=[log])
    assert logged[0].rule == "configured-secret"
    assert "booker_canary" not in repr(logged)


def test_public_api_and_logs_do_not_expose_configured_canary(client, monkeypatch, caplog, capsys):
    canary = "booker_canary_" + "M4nR8tY2pL6qW9xZ"
    monkeypatch.setattr(settings, "webhook_secret", canary)
    monkeypatch.setattr(settings, "email_api_key", canary)
    monkeypatch.setattr(settings, "sms_api_key", canary)
    monkeypatch.setattr(settings, "object_storage_secret_key", canary)
    for endpoint in ("/health", "/readiness", "/categories", "/service-templates"):
        response = client.get(endpoint)
        assert response.status_code in {200, 503}
        assert canary not in response.text
    denied = client.get("/admin/support/tickets")
    assert denied.status_code in {401, 403}
    assert canary not in denied.text
    bad_webhook = client.post(
        "/payments/webhook",
        json={"event_id": "canary-evt", "payment_id": "missing", "status": "succeeded", "signature": "invalid"},
    )
    assert bad_webhook.status_code in {400, 401, 404, 422}
    assert canary not in bad_webhook.text
    output = capsys.readouterr()
    assert canary not in caplog.text + output.out + output.err


def test_scanner_cli_does_not_echo_a_synthetic_token(tmp_path):
    token = "ghp_" + "A" * 30
    root = tmp_path / "repo"
    root.mkdir()
    subprocess.run(["git", "init", "-q", str(root)], check=True)
    (root / f"{token}.txt").write_text(token, encoding="utf-8")
    env = {**os.environ, "BOOKER_WEBHOOK_SECRET": ""}
    script = ROOT / "scripts/check_secret_exposure.py"
    # The CLI uses its own checkout root; copy the scanner into the synthetic repo.
    scripts = root / "scripts"
    scripts.mkdir()
    (scripts / script.name).write_bytes(script.read_bytes())
    result = subprocess.run(
        [sys.executable, str(scripts / script.name), "--source"],
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    assert result.returncode != 0
    assert "provider-token" in result.stdout
    assert token not in result.stdout + result.stderr
