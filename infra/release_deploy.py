"""Build an isolated Booker release, switch one symlink, and roll back on failure.

Run on the VPS only after the candidate source has been uploaded to
``/opt/booker/releases/<id>``. This module has no SSH or network upload code.
"""

from __future__ import annotations

import argparse
import fcntl
import hashlib
import json
import os
import pwd
import re
import shutil
import signal
import stat
import subprocess
import sys
import tempfile
import time
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path

ID_PATTERN = re.compile(r"^[0-9]{8}T[0-9]{6}Z-[0-9a-f]{12}$")
SHA_PATTERN = re.compile(r"^(?:[0-9a-f]{40}|UNKNOWN)$")
SCHEMA_FILES = (
    "apps/api/booker_api/db.py",
    "apps/api/booker_api/models.py",
)
ARTIFACT_FILES = (
    "apps/api/requirements-prod.lock",
    "apps/web/package-lock.json",
    "apps/web/.next/BUILD_ID",
    "infra/systemd/booker-api.service",
    "infra/systemd/booker-web.service",
    "infra/nginx/bukergo.ru.conf",
    "infra/nginx/booker-common-headers.conf",
    "infra/nginx/booker-https-headers.conf",
)


class ReleaseError(RuntimeError):
    pass


def _digest(path: Path) -> str:
    value = hashlib.sha256()
    with path.open("rb") as source:
        for part in iter(lambda: source.read(1024 * 1024), b""):
            value.update(part)
    return value.hexdigest()


def _sync_directory(path: Path) -> None:
    descriptor = os.open(path, os.O_RDONLY | os.O_DIRECTORY | os.O_NOFOLLOW)
    try:
        os.fsync(descriptor)
    finally:
        os.close(descriptor)


def _atomic_bytes(path: Path, content: bytes, mode: int = 0o600) -> None:
    if path.is_symlink() or path.parent.is_symlink():
        raise ReleaseError("unsafe output path")
    descriptor, temporary = tempfile.mkstemp(prefix=".booker-deploy-", dir=path.parent)
    try:
        os.fchmod(descriptor, mode)
        with os.fdopen(descriptor, "wb") as output:
            output.write(content)
            output.flush()
            os.fsync(output.fileno())
        os.replace(temporary, path)
        _sync_directory(path.parent)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def _atomic_link(path: Path, target: str) -> None:
    temporary = path.parent / f".booker-link-{os.getpid()}"
    if temporary.exists() or temporary.is_symlink():
        raise ReleaseError("temporary deployment link exists")
    try:
        temporary.symlink_to(target)
        os.replace(temporary, path)
        _sync_directory(path.parent)
    finally:
        temporary.unlink(missing_ok=True)


def _default_runner(args: list[str], *, cwd: Path | None = None, env: dict | None = None) -> None:
    subprocess.run(args, cwd=cwd, env=env, check=True, timeout=900)


class ReleaseDeployer:
    def __init__(
        self, root: Path, release_id: str, *, source_sha: str = "UNKNOWN",
        systemd_dir: Path = Path("/etc/systemd/system"),
        nginx_dir: Path = Path("/etc/nginx/sites-available"),
        enabled_dir: Path = Path("/etc/nginx/sites-enabled"),
        env_file: Path = Path("/etc/booker/booker-api.env"),
        cron_dir: Path = Path("/etc/cron.d"),
        runner: Callable = _default_runner,
    ) -> None:
        if not root.is_absolute() or root.is_symlink() or root.resolve() != root:
            raise ReleaseError("deployment root must be a real absolute directory")
        if not ID_PATTERN.fullmatch(release_id) or not SHA_PATTERN.fullmatch(source_sha):
            raise ReleaseError("invalid release identity")
        self.root = root
        self.release_id = release_id
        self.release = root / "releases" / release_id
        self.shared = root / "shared"
        self.state_path = self.shared / "deploy-state.json"
        self.systemd_dir = systemd_dir
        self.nginx_dir = nginx_dir
        self.enabled_dir = enabled_dir
        self.env_file = env_file
        self.source_sha = source_sha
        self.runner = runner
        self.configs = {
            "api": systemd_dir / "booker-api.service",
            "web": systemd_dir / "booker-web.service",
            "nginx": nginx_dir / "bukergo.ru.conf",
            "enabled": enabled_dir / "bukergo.ru.conf",
            "cron": cron_dir / "booker-backup",
        }

    def _run(self, *args: str, cwd: Path | None = None, env: dict | None = None) -> None:
        self.runner(list(args), cwd=cwd, env=env)

    def _paths(self) -> None:
        for path in (self.root, self.root / "releases", self.release):
            if not path.is_dir() or path.is_symlink():
                raise ReleaseError("release path is missing or symlinked")
        if self.release.resolve() != self.release:
            raise ReleaseError("release path escapes deployment root")
        self.shared.mkdir(mode=0o700, exist_ok=True)
        if self.shared.is_symlink() or not self.shared.is_dir():
            raise ReleaseError("unsafe shared directory")
        self.shared.chmod(0o700)
        if not self.env_file.is_file() or self.env_file.is_symlink():
            raise ReleaseError("protected production environment is missing")

    def current(self) -> str | None:
        path = self.root / "current"
        if not path.exists() and not path.is_symlink():
            return None
        if not path.is_symlink():
            raise ReleaseError("current is not a release symlink")
        target = os.readlink(path)
        if not target.startswith("releases/"):
            raise ReleaseError("current points outside releases")
        release_id = target.removeprefix("releases/")
        if not ID_PATTERN.fullmatch(release_id) or target != f"releases/{release_id}":
            raise ReleaseError("current has an invalid release target")
        destination = self.root / "releases" / release_id
        if not destination.is_dir() or destination.is_symlink():
            raise ReleaseError("current release is missing")
        return release_id

    def _set_current(self, release_id: str | None) -> None:
        self.current()  # reject an unsafe pre-existing current path
        path = self.root / "current"
        if release_id is None:
            path.unlink(missing_ok=True)
            _sync_directory(self.root)
            return
        if not ID_PATTERN.fullmatch(release_id):
            raise ReleaseError("invalid current release id")
        destination = self.root / "releases" / release_id
        if not destination.is_dir() or destination.is_symlink():
            raise ReleaseError("current target is not a release")
        _atomic_link(path, f"releases/{release_id}")

    @staticmethod
    def _schema_digest(source: Path) -> str:
        paths = [source / item for item in SCHEMA_FILES]
        paths.extend(sorted((source / "apps/api/alembic/versions").glob("*.py")))
        if len(paths) <= len(SCHEMA_FILES) or any(not path.is_file() for path in paths):
            raise ReleaseError("schema contract files are incomplete")
        digest = hashlib.sha256()
        for path in paths:
            digest.update(str(path.relative_to(source)).encode())
            digest.update(bytes.fromhex(_digest(path)))
        return digest.hexdigest()

    def _schema_gate(self, previous: str | None) -> None:
        old_source = self.root / "releases" / previous if previous else self.root
        old_models = old_source / SCHEMA_FILES[1]
        if not old_models.is_file():
            # New installs may create their first DB. Existing SQLite/PG data need a baseline.
            env_text = self.env_file.read_text(encoding="utf-8")
            if (self.root / "data/booker.db").exists() or "BOOKER_DATABASE_URL=postgres" in env_text:
                raise ReleaseError("existing database has no comparable schema baseline")
            return
        if self._schema_digest(old_source) != self._schema_digest(self.release):
            self._reviewed_schema_gate()

    def _reviewed_schema_gate(self) -> None:
        """Allow a changed schema only after a separate, evidenced migration phase."""
        values = {}
        database_url = ""
        for raw in self.env_file.read_text(encoding="utf-8").splitlines():
            if raw.startswith("BOOKER_DATABASE_URL="):
                database_url = raw.split("=", 1)[1].strip().strip('"')
            if raw.startswith("BOOKER_SCHEMA_") and "=" in raw:
                key, value = raw.split("=", 1)
                values[key] = value.strip().strip('"')
        required = ("MANIFEST_SHA256", "MIGRATION_EVIDENCE_SHA256", "REHEARSAL_SHA256",
                    "BACKUP_SHA256", "SOURCE_REVISION")
        if any(not values.get("BOOKER_SCHEMA_" + key) for key in required):
            raise ReleaseError("schema or migration code changed; reviewed evidence missing")
        if database_url != "sqlite:////opt/booker/data/booker.db":
            raise ReleaseError("active database revision is unverified; PostgreSQL gate unavailable")
        from schema_release import (
            SchemaReleaseError,
            digest,
            sqlite_state,
            verify_manifest,
        )

        manifest_path = self.release / "infra/schema-release-manifest.v1.json"
        evidence_path = self.env_file.parent / "schema-migration-evidence.json"
        if (not manifest_path.is_file() or manifest_path.is_symlink()
                or not evidence_path.is_file() or evidence_path.is_symlink()):
            raise ReleaseError("schema manifest or migration evidence missing")
        if digest(evidence_path) != values["BOOKER_SCHEMA_MIGRATION_EVIDENCE_SHA256"]:
            raise ReleaseError("migration evidence hash mismatch")
        try:
            manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
            evidence = json.loads(evidence_path.read_text(encoding="utf-8"))
            source_revision = values["BOOKER_SCHEMA_SOURCE_REVISION"]
            verify_manifest(
                manifest, self.release / "apps/api/alembic/versions",
                exact_manifest_sha256=values["BOOKER_SCHEMA_MANIFEST_SHA256"],
                source_state=source_revision,
                actual_state=evidence.get("observed_source_revision", "unknown"),
                rehearsal_sha256=values["BOOKER_SCHEMA_REHEARSAL_SHA256"],
                backup_sha256=values["BOOKER_SCHEMA_BACKUP_SHA256"],
            )
            if (evidence.get("status") != "verified"
                    or evidence.get("manifest_sha256") != values["BOOKER_SCHEMA_MANIFEST_SHA256"]
                    or evidence.get("rehearsal_evidence_sha256") != values["BOOKER_SCHEMA_REHEARSAL_SHA256"]
                    or evidence.get("backup_archive_sha256") != values["BOOKER_SCHEMA_BACKUP_SHA256"]
                    or evidence.get("target_head") != manifest["target_head"]):
                raise ReleaseError("separate migration evidence is incomplete")
            # Runtime startup may alter SQLite tables. Never infer its revision from
            # a table shape; a versionless create_all database remains unknown.
            if sqlite_state(self.root / "data/booker.db") != manifest["target_head"]:
                raise ReleaseError("production SQLite target revision is unverified")
        except (OSError, ValueError, KeyError, SchemaReleaseError) as exc:
            raise ReleaseError("schema migration review failed closed") from exc

    def _candidate_nginx(self) -> None:
        source = self.release / "infra/nginx"
        with tempfile.TemporaryDirectory(prefix="booker-nginx-check-") as directory:
            target = Path(directory)
            common = target / "common.conf"
            https = target / "https.conf"
            site = target / "site.conf"
            common.write_bytes((source / "booker-common-headers.conf").read_bytes())
            https.write_text(
                (source / "booker-https-headers.conf").read_text(encoding="utf-8")
                .replace("/opt/booker/current/infra/nginx/booker-common-headers.conf", str(common)),
                encoding="utf-8",
            )
            site.write_text(
                (source / "bukergo.ru.conf").read_text(encoding="utf-8")
                .replace("/opt/booker/current/infra/nginx/booker-https-headers.conf", str(https))
                .replace("/opt/booker/current/infra/nginx/booker-common-headers.conf", str(common))
                .replace("/opt/booker/current/", f"{self.release}/"),
                encoding="utf-8",
            )
            main = target / "nginx.conf"
            main.write_text(
                f"pid {target}/nginx.pid;\nerror_log stderr;\nevents {{}}\nhttp {{ include {site}; }}\n",
                encoding="utf-8",
            )
            self._run("nginx", "-t", "-q", "-c", str(main), "-p", f"{target}/")

    def prepare(self, previous: str | None) -> None:
        self._schema_gate(previous)
        python = self.release / ".venv/bin/python"
        pip = self.release / ".venv/bin/pip"
        self._run("python3", "-m", "venv", str(self.release / ".venv"))
        self._run(str(pip), "install", "--no-input", "-r", str(self.release / "apps/api/requirements-prod.lock"))
        self._run(str(pip), "install", "--no-input", "--no-deps", "-e", str(self.release / "apps/api"))
        self._run(str(pip), "check")
        self._run(
            str(python), str(self.release / "infra/preflight_booker_api.py"),
            str(self.release / "infra/systemd/booker-api.service"), str(self.env_file),
            cwd=self.release / "apps/api",
        )
        web = self.release / "apps/web"
        self._run("npm", "ci", "--silent", cwd=web)
        build_env = {**os.environ, "NEXT_PUBLIC_API_URL": "/api",
                     "NEXT_PUBLIC_SITE_URL": "https://bukergo.ru",
                     "BOOKER_INTERNAL_API_URL": "http://127.0.0.1:8030"}
        self._run("npm", "run", "build", cwd=web, env=build_env)
        if not (web / ".next/BUILD_ID").is_file():
            raise ReleaseError("web build has no BUILD_ID")
        self._run(
            str(python), str(self.release / "scripts/check_secret_exposure.py"),
            "--build", "--env-file", str(self.env_file), cwd=self.release,
        )
        self._candidate_nginx()
        try:
            pwd.getpwnam("booker")
        except KeyError:
            self._run("useradd", "--system", "--home", "/var/lib/booker",
                      "--create-home", "--shell", "/usr/sbin/nologin", "booker")
        self._run("chown", "-R", "booker:booker", str(web / ".next"))
        _atomic_bytes(self.release / ".prepared", b"ready\n")

    def _snapshot(self) -> Path:
        snapshot = self.shared / "deploy-snapshots" / self.release_id
        snapshot.parent.mkdir(mode=0o700, exist_ok=True)
        if snapshot.parent.is_symlink() or snapshot.parent.resolve() != snapshot.parent:
            raise ReleaseError("unsafe deploy snapshot directory")
        snapshot.mkdir(mode=0o700, exist_ok=False)
        values = {}
        for name, path in self.configs.items():
            if path.is_symlink():
                values[name] = {"kind": "symlink", "target": os.readlink(path)}
            elif path.is_file():
                values[name] = {"kind": "file", "mode": stat.S_IMODE(path.stat().st_mode)}
                _atomic_bytes(snapshot / name, path.read_bytes())
            elif not path.exists():
                values[name] = {"kind": "missing"}
            else:
                raise ReleaseError("unexpected installed config type")
        _atomic_bytes(snapshot / "manifest.json", json.dumps(values, sort_keys=True).encode())
        return snapshot

    def _restore_configs(self, snapshot: Path) -> dict:
        manifest = json.loads((snapshot / "manifest.json").read_text(encoding="utf-8"))
        for name, path in self.configs.items():
            previous = manifest[name]
            path.parent.mkdir(parents=True, exist_ok=True)
            if previous["kind"] == "missing":
                if path.is_file() or path.is_symlink():
                    path.unlink()
            elif previous["kind"] == "symlink":
                _atomic_link(path, previous["target"])
            elif previous["kind"] == "file":
                _atomic_bytes(path, (snapshot / name).read_bytes(), previous["mode"])
            else:
                raise ReleaseError("invalid config snapshot")
        return manifest

    def _install_configs(self) -> None:
        sources = {
            "api": self.release / "infra/systemd/booker-api.service",
            "web": self.release / "infra/systemd/booker-web.service",
            "nginx": self.release / "infra/nginx/bukergo.ru.conf",
            "cron": self.release / "infra/cron-booker-backup.example",
        }
        for name, source in sources.items():
            target = self.configs[name]
            target.parent.mkdir(parents=True, exist_ok=True)
            _atomic_bytes(target, source.read_bytes(), 0o644)
        self.configs["enabled"].parent.mkdir(parents=True, exist_ok=True)
        _atomic_link(self.configs["enabled"], str(self.configs["nginx"]))

    def _probe(self, *, legacy: bool = False) -> None:
        path = "/health" if legacy else "/internal/readiness"
        self._run("curl", "-fS", "--retry", "15", "--retry-connrefused", "--retry-delay", "3",
                  "--max-time", "8", f"http://127.0.0.1:8030{path}")
        self._run("curl", "-fS", "--retry", "15", "--retry-connrefused", "--retry-delay", "3",
                  "--max-time", "8", "http://127.0.0.1:3030/")

    def _rollback(self, state: dict) -> None:
        problems = []
        previous = state["previous"]
        snapshot = Path(state["snapshot"])
        if (
            state.get("version") != 1
            or not ID_PATTERN.fullmatch(state.get("release_id", ""))
            or snapshot != self.shared / "deploy-snapshots" / state["release_id"]
            or snapshot.is_symlink()
            or (previous is not None and not ID_PATTERN.fullmatch(previous))
        ):
            raise ReleaseError("unsafe interrupted deployment state")
        try:
            self._set_current(previous)
            prior_configs = self._restore_configs(snapshot)
            self._run("systemctl", "daemon-reload")
            if prior_configs["api"]["kind"] != "missing":
                self._run("systemctl", "restart", "booker-api", "booker-web")
            else:
                self._run("systemctl", "stop", "booker-api", "booker-web")
            if prior_configs["nginx"]["kind"] != "missing":
                self._run("nginx", "-t")
                self._run("nginx", "-s", "reload")
            if prior_configs["api"]["kind"] != "missing":
                self._probe(legacy=previous is None)
        except (OSError, subprocess.SubprocessError, ReleaseError, ValueError) as exc:
            problems.append(type(exc).__name__)
        if problems:
            state["phase"] = "rollback_failed"
            _atomic_bytes(self.state_path, json.dumps(state, sort_keys=True).encode())
            raise ReleaseError("CRITICAL: rollback failed; previous release retained")
        self.state_path.unlink(missing_ok=True)
        _sync_directory(self.shared)

    def _write_evidence(self, previous: str | None) -> None:
        hashes = {name: _digest(self.release / name) for name in ARTIFACT_FILES}
        payload = {
            "version": 1, "release_id": self.release_id, "previous_release": previous,
            "source_sha": self.source_sha, "completed_at": datetime.now(timezone.utc).isoformat(),
            "artifacts_sha256": hashes,
            "checks": ["schema_gate", "prod_preflight", "web_build", "secret_build_gate",
                       "candidate_nginx_syntax", "api_readiness", "web_http", "nginx_reload"],
            "data_rollback": "not_atomic",
        }
        _atomic_bytes(self.release / "release-evidence.json", json.dumps(payload, sort_keys=True).encode())

    def _cleanup(self, previous: str | None) -> None:
        releases = self.root / "releases"
        protected = {self.release_id, previous}
        cutoff = time.time() - 7 * 24 * 3600
        for path in releases.iterdir():
            if (
                path.is_dir() and not path.is_symlink()
                and ID_PATTERN.fullmatch(path.name) and path.name not in protected
                and not (path / "release-evidence.json").exists()
                and path.stat().st_mtime < cutoff
            ):
                if path.parent != releases or path.resolve() != path:
                    raise ReleaseError("unsafe stale release cleanup target")
                shutil.rmtree(path)
        candidates = sorted(
            (path for path in releases.iterdir()
             if path.is_dir() and not path.is_symlink()
             and ID_PATTERN.fullmatch(path.name)
             and (path / "release-evidence.json").is_file()
             and path.name not in protected),
            key=lambda path: path.stat().st_mtime_ns, reverse=True,
        )
        for path in candidates[3:]:
            if path.parent != releases or path.resolve() != path or path.name in protected:
                raise ReleaseError("unsafe release cleanup target")
            shutil.rmtree(path)

    def _switch(self, previous: str | None) -> None:
        snapshot = self._snapshot()
        state = {"version": 1, "phase": "switching", "release_id": self.release_id,
                 "previous": previous, "snapshot": str(snapshot)}
        _atomic_bytes(self.state_path, json.dumps(state, sort_keys=True).encode())
        try:
            if not (self.release / ".prepared").is_file():
                raise ReleaseError("candidate release was not prepared")
            self._install_configs()
            self._set_current(self.release_id)
            self._run("systemctl", "daemon-reload")
            self._run("systemctl", "restart", "booker-api", "booker-web")
            self._run("nginx", "-t")
            self._run("nginx", "-s", "reload")
            self._run("systemctl", "is-active", "booker-api", "booker-web")
            self._probe()
            self._write_evidence(previous)
        except (OSError, subprocess.SubprocessError, ReleaseError, ValueError) as exc:
            self._rollback(state)
            raise ReleaseError("candidate release failed after switch; previous release restored") from exc
        state["phase"] = "committed"
        _atomic_bytes(self.state_path, json.dumps(state, sort_keys=True).encode())
        self.state_path.unlink(missing_ok=True)
        _sync_directory(self.shared)
        try:
            self._cleanup(previous)
        except (OSError, ReleaseError) as exc:
            print(f"WARNING: release cleanup deferred: {type(exc).__name__}", file=sys.stderr)

    def run(self) -> None:
        self._paths()
        lock_path = self.shared / ".deploy.lock"
        descriptor = os.open(lock_path, os.O_CREAT | os.O_RDWR | os.O_NOFOLLOW, 0o600)
        old_term = signal.getsignal(signal.SIGTERM)
        old_int = signal.getsignal(signal.SIGINT)

        def interrupted(_signal, _frame):
            raise ReleaseError("deployment interrupted")

        try:
            fcntl.flock(descriptor, fcntl.LOCK_EX | fcntl.LOCK_NB)
            signal.signal(signal.SIGTERM, interrupted)
            signal.signal(signal.SIGINT, interrupted)
            if self.state_path.exists():
                state = json.loads(self.state_path.read_text(encoding="utf-8"))
                if state.get("version") != 1 or state.get("release_id") is None:
                    raise ReleaseError("unsafe interrupted deployment state")
                if state.get("phase") == "committed":
                    if self.current() != state["release_id"] or not (
                        self.root / "releases" / state["release_id"] / "release-evidence.json"
                    ).is_file():
                        raise ReleaseError("committed deployment state does not match current")
                    self.state_path.unlink()
                    _sync_directory(self.shared)
                else:
                    self._rollback(state)
            previous = self.current()
            try:
                self.prepare(previous)
            except subprocess.SubprocessError as exc:
                raise ReleaseError("candidate preparation failed; active release unchanged") from exc
            self._switch(previous)
        finally:
            signal.signal(signal.SIGTERM, old_term)
            signal.signal(signal.SIGINT, old_int)
            fcntl.flock(descriptor, fcntl.LOCK_UN)
            os.close(descriptor)


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("release_id")
    parser.add_argument("--root", type=Path, default=Path("/opt/booker"))
    parser.add_argument("--source-sha", default="UNKNOWN")
    args = parser.parse_args()
    try:
        ReleaseDeployer(args.root, args.release_id, source_sha=args.source_sha).run()
    except (OSError, subprocess.SubprocessError, ReleaseError, ValueError):
        raise SystemExit("Booker release failed; inspect local deploy log and state") from None


if __name__ == "__main__":
    main()
