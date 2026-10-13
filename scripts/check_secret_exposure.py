"""High-confidence secret exposure gate; never prints matched values."""

from __future__ import annotations

import argparse
import hashlib
import math
import os
import re
import shlex
import subprocess
import tempfile
from collections import Counter
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlsplit

ROOT = Path(__file__).resolve().parents[1]
MAX_TEXT_BYTES = 10 * 1024 * 1024
SKIP_PARTS = {".git", ".venv", "venv", "node_modules", ".next", "outputs", "__pycache__"}
SKIP_PREFIXES = ("data/uploads/", "apps/api/data/uploads/", "apps/web/test-results/")
BUILD_DIRS = ("apps/web/.next/static", "apps/web/.next/server", "apps/web/.next/standalone")
ARTIFACT_DIRS = ("apps/web/test-results", "apps/web/playwright-report", "apps/api/test-results", "logs")
DEPLOY_EXCLUDES = "infra/rsync-booker-excludes.txt"
SAFE_BINARY_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".gif", ".ico", ".woff", ".woff2"}
SENSITIVE_ENV = (
    "BOOKER_WEBHOOK_SECRET",
    "BOOKER_PAYMENT_SECRET_KEY",
    "BOOKER_EMAIL_API_KEY",
    "BOOKER_SMS_API_KEY",
    "BOOKER_OBJECT_STORAGE_SECRET_KEY",
)

TOKEN = re.compile(
    r"(?<![\w-])(?:sk_live_[A-Za-z0-9_-]{12,}|gh[pousr]_[A-Za-z0-9]{20,}|"
    r"github_pat_[A-Za-z0-9_]{20,}|xox[baprs]-[A-Za-z0-9-]{12,}|AKIA[A-Z0-9]{16})"
)
TOKEN_BYTES = re.compile(TOKEN.pattern.encode())
PRIVATE_KEY = re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----")
PRIVATE_KEY_BYTES = re.compile(PRIVATE_KEY.pattern.encode())
DATABASE_CREDENTIAL = re.compile(
    r"(?i)\b(?:postgresql(?:\+psycopg)?|postgres|mysql(?:\+\w+)?)://"
    r"[^\s:/@]+:(?P<password>[^\s/@]+)@(?P<host>[^\s/]+)"
)
ASSIGNMENT = re.compile(
    r"(?i)(?:^|[\s,{])(?:[\"']?)(?P<name>[A-Za-z_][\w-]*(?:secret|password|token|api[_-]?key|private[_-]?key)[\w-]*)"
    r"(?:[\"']?)[ \t]*[:=][ \t]*(?P<quote>[\"']?)(?P<value>[^\s,;\"'}]+)",
    re.MULTILINE,
)
PUBLIC_NAME = re.compile(r"\bNEXT_PUBLIC_[A-Z0-9_]*(?:SECRET|PASSWORD|TOKEN|API_KEY|PRIVATE_KEY)[A-Z0-9_]*\b")

# Only known fake fixture tokens, bound to their test file. Add by review, never globally.
FAKE_FIXTURE_SHA256: dict[str, frozenset[str]] = {
    "README.md": frozenset(
        {"09f025915c1b54a80b69ac25f9bfac6c6993a6fa4dee5d25ccdfa1d30fe9ea04"}
    ),
    "apps/api/tests/test_backup_restore.py": frozenset(
        {"2bb80d537b1da3e38bd30361aa855686bde0eacd7162fef6a25fe97bf527a25b"}
    ),
    "apps/api/tests/test_postgres_harness.py": frozenset(
        {
            "148de9c5a7a44d19e56cd9ae1a554bf67847afb0c58f6e12fa29ac7ddfca9940",
            "50d858e0985ecc7f60418aaf0cc5ab587f42c2570a884095a9e8ccacd0f6545c",
        }
    ),
    "apps/api/tests/test_secret_exposure_gate.py": frozenset(
        {
            "e2d7ec6505033bfed15a5e5d2313854e3d29cebf4fe4ff409d9f49dea0c59d68",
            "9ae306c7ddd3f1674b7a4f52ebd528320f60ef09009268d0a4cf365d5ee491b4",
            "d74ff0ee8da3b9806b18c877dbf29bbde50b5bd8e4dad7a3a725000feb82e8f1",
        }
    ),
    "apps/api/tests/test_production_config.py": frozenset(
        {"7956dd4924a8d3341087b0669331f4d9f7d711fbc156e1f1d8fba7c496b9daab"}
    ),
    "apps/api/tests/test_support_agent.py": frozenset(
        {
            "4c41ea8d6f087b69fe37017812d7eb24771e6560c2e57f0d03686879a7fa8ada",
            "d25acb640d39af77a9a86860289be42118c6a4bc504ed6a43c407dd34f6834dd",
        }
    ),
    "apps/api/tests/test_support_secret_backfill.py": frozenset(
        {"4c41ea8d6f087b69fe37017812d7eb24771e6560c2e57f0d03686879a7fa8ada"}
    ),
    "apps/api/tests/test_support_security.py": frozenset(
        {
            "4c41ea8d6f087b69fe37017812d7eb24771e6560c2e57f0d03686879a7fa8ada",
            "554879fdd33b5d3d908a950e6c62bebd48b3a277cfc36c3f61e1e3679c158095",
        }
    ),
    # Fixed synthetic Base32 TOTP values used only by the S06 test module.
    "apps/api/tests/test_identity_s06.py": frozenset(
        {
            "b6f847712ce64a47a9fb17f06f7cf88631eca859d9d68851c66079ca98641c7d",
            "358cd47836776a4d1cfedecf8aad2aab5aedd84162fdfe49879492c6f95ea788",
        }
    ),
    "docs/ops/POSTGRES_STAGING_PROOF.md": frozenset(
        {"09f025915c1b54a80b69ac25f9bfac6c6993a6fa4dee5d25ccdfa1d30fe9ea04"}
    ),
    "docs/ops/PROD_INFRA.md": frozenset(
        {"09f025915c1b54a80b69ac25f9bfac6c6993a6fa4dee5d25ccdfa1d30fe9ea04"}
    ),
    "infra/migrate-postgres-docker.sh": frozenset(
        {"09f025915c1b54a80b69ac25f9bfac6c6993a6fa4dee5d25ccdfa1d30fe9ea04"}
    ),
}


@dataclass(frozen=True)
class Finding:
    path: str
    line: int
    rule: str


def _entropy(value: str) -> float:
    counts = Counter(value)
    return -sum((count / len(value)) * math.log2(count / len(value)) for count in counts.values())


def _placeholder(value: str) -> bool:
    lowered = value.lower()
    return (
        not value
        or value in {'""', "''"}
        or lowered in {"none", "null", "undefined", "disabled", "pass", "password", "user"}
        or lowered.startswith(("{{", "<set", "${", "dev-", "test-", "example-", "placeholder"))
    )


def _fake_fixture(path: str, value: str) -> bool:
    digest = hashlib.sha256(value.encode()).hexdigest()
    return digest in FAKE_FIXTURE_SHA256.get(path, frozenset())


def scan_text(path: str, content: str, *, env_values: tuple[str, ...] = ()) -> list[Finding]:
    found: set[Finding] = set()

    def add(position: int, rule: str) -> None:
        found.add(Finding(path, content.count("\n", 0, position) + 1, rule))

    for match in TOKEN.finditer(content):
        if not _fake_fixture(path, match.group()):
            add(match.start(), "provider-token")
    for match in PRIVATE_KEY.finditer(content):
        add(match.start(), "private-key")
    for match in DATABASE_CREDENTIAL.finditer(content):
        password = match.group("password")
        template = (
            (password.startswith("{{") and password.endswith("}}"))
            or (password in {"PASS", "PASSWORD"} and match.group("host").startswith("HOST"))
        )
        if not template and not _fake_fixture(path, password):
            add(match.start("password"), "database-url-credential")
    for match in PUBLIC_NAME.finditer(content):
        add(match.start(), "public-env-name")
    for match in ASSIGNMENT.finditer(content):
        value = match.group("value")
        if (
            not match.group("name").upper().endswith(("_HEADER", "_NAME", "_FIELD"))
            and
            (match.group("quote") or match.group("name").isupper())
            and not _placeholder(value)
            and not _fake_fixture(path, value)
            and len(value) >= 20
            and _entropy(value) >= 3.5
        ):
            add(match.start("value"), "secret-assignment")
    for value in env_values:
        if len(value) >= 8:
            position = content.find(value)
            while position >= 0:
                add(position, "configured-secret")
                position = content.find(value, position + len(value))
        elif len(value) >= 3:
            quoted = re.compile(rf"[\"']{re.escape(value)}[\"']")
            for match in quoted.finditer(content):
                add(match.start(), "configured-short-secret")
    return sorted(found, key=lambda item: (item.path, item.line, item.rule))


def source_paths(root: Path) -> list[Path]:
    listed = subprocess.run(
        ["git", "ls-files", "-c", "-o", "--exclude-standard", "-z"],
        cwd=root,
        check=True,
        capture_output=True,
    ).stdout
    paths: list[Path] = []
    for raw in listed.split(b"\0"):
        if not raw:
            continue
        relative = os.fsdecode(raw)
        if any(part in SKIP_PARTS for part in Path(relative).parts):
            continue
        # Isolated Next/Playwright distDir outputs are untracked build products.
        if relative.startswith(("apps/web/.next-e2e-", "apps/web/.next-preview-")):
            continue
        if relative.startswith(SKIP_PREFIXES):
            continue
        path = root / relative
        if path.is_symlink() or not path.is_file():
            continue
        paths.append(path)
    return sorted(set(paths))


def build_paths(root: Path) -> list[Path]:
    paths: list[Path] = []
    for directory in BUILD_DIRS:
        target = root / directory
        if target.exists():
            paths.extend(path for path in target.rglob("*") if path.is_file() and not path.is_symlink())
    return sorted(set(paths))


def deploy_paths(root: Path) -> tuple[list[Path], list[Finding]]:
    exclusions = root / DEPLOY_EXCLUDES
    if not exclusions.is_file():
        return [], [Finding("deploy", 0, "deploy-exclusions-missing")]
    with tempfile.TemporaryDirectory(prefix="booker-deploy-inventory-") as target:
        inventory = subprocess.run(
            [
                "rsync", "-a", "--dry-run", f"--exclude-from={exclusions}",
                "--out-format=%n", f"{root}/", f"{target}/",
            ],
            check=True,
            capture_output=True,
            text=True,
        ).stdout
    paths: list[Path] = []
    issues: list[Finding] = []
    for name in inventory.splitlines():
        if name in {"./", ""} or name.endswith("/"):
            continue
        candidate = root / name
        if not candidate.exists() and not candidate.is_symlink():
            issues.append(Finding("deploy", 0, "deploy-inventory-ambiguous"))
            continue
        if candidate.is_symlink():
            issues.append(Finding(name, 0, "deploy-symlink"))
            continue
        if candidate.is_file():
            if candidate.name.startswith(".env") or candidate.suffix.lower() in {
                ".pem", ".key", ".p12", ".pfx",
            }:
                issues.append(Finding(name, 0, "deploy-sensitive-filename"))
            paths.append(candidate)
    return paths, issues


def scan_file(root: Path, path: Path, *, env_values: tuple[str, ...], payload: bool = False) -> list[Finding]:
    relative = path.relative_to(root).as_posix()
    if path.stat().st_size > MAX_TEXT_BYTES:
        return [Finding(relative, 0, "oversized-unscanned")]
    raw = path.read_bytes()
    if b"\0" in raw[:4096]:
        return scan_binary(relative, raw, env_values, payload=payload, suffix=path.suffix.lower())
    try:
        content = raw.decode("utf-8")
    except UnicodeDecodeError:
        return scan_binary(relative, raw, env_values, payload=payload, suffix=path.suffix.lower())
    return scan_text(relative, content, env_values=env_values)


def scan_binary(
    path: str, raw: bytes, env_values: tuple[str, ...], *, payload: bool, suffix: str,
) -> list[Finding]:
    findings: set[Finding] = set()
    for match in TOKEN_BYTES.finditer(raw):
        if not _fake_fixture(path, match.group().decode("ascii")):
            findings.add(Finding(path, 0, "provider-token-binary"))
    if PRIVATE_KEY_BYTES.search(raw):
        findings.add(Finding(path, 0, "private-key-binary"))
    for value in env_values:
        if len(value) >= 8 and value.encode() in raw:
            findings.add(Finding(path, 0, "configured-secret-binary"))
        elif 3 <= len(value) < 8 and (
            b"'" + value.encode() + b"'" in raw or b'"' + value.encode() + b'"' in raw
        ):
            findings.add(Finding(path, 0, "configured-short-secret-binary"))
    if payload and suffix not in SAFE_BINARY_SUFFIXES:
        findings.add(Finding(path, 0, "deploy-binary-unscanned"))
    return sorted(findings, key=lambda item: item.rule)

def env_file_values(path: Path) -> tuple[str, ...]:
    values: list[str] = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.split(None, 1)[0] == "export":
            raise ValueError("invalid env file syntax")
        assignment = shlex.split(line)
        if len(assignment) != 1 or "=" not in assignment[0]:
            raise ValueError("invalid env file assignment")
        name, value = assignment[0].split("=", 1)
        if name in SENSITIVE_ENV and value and not _placeholder(value):
            values.append(value)
        if name == "BOOKER_DATABASE_URL" and value:
            parsed = urlsplit(value)
            if parsed.password:
                values.append(parsed.password)
            values.append(value)
    return tuple(values)


def run(
    *, root: Path, source: bool, build: bool, artifacts: list[Path],
    deploy: bool = False, extra_values: tuple[str, ...] = (),
) -> list[Finding]:
    paths: list[Path] = []
    deploy_set: set[Path] = set()
    findings: list[Finding] = []
    if source:
        paths.extend(source_paths(root))
    if build:
        if not (root / "apps/web/.next/BUILD_ID").is_file():
            return [Finding("apps/web/.next", 0, "build-missing")]
        paths.extend(build_paths(root))
    if deploy:
        deploy_list, deploy_issues = deploy_paths(root)
        deploy_set.update(deploy_list)
        paths.extend(deploy_list)
        findings.extend(deploy_issues)
    for artifact in artifacts:
        resolved = artifact.resolve()
        if not any(
            resolved == root / allowed or root / allowed in resolved.parents
            for allowed in ARTIFACT_DIRS
        ):
            return [Finding("artifact", 0, "artifact-path-not-approved")]
        if resolved.is_dir():
            paths.extend(path for path in resolved.rglob("*") if path.is_file() and not path.is_symlink())
        elif resolved.is_file():
            paths.append(resolved)
        else:
            return [Finding(str(artifact), 0, "artifact-missing")]
    env_values = extra_values + tuple(
        value for name in SENSITIVE_ENV if (value := os.environ.get(name, "")) and not _placeholder(value)
    )
    database_url = os.environ.get("BOOKER_DATABASE_URL", "")
    if database_url:
        parsed = urlsplit(database_url)
        if parsed.password:
            env_values += (parsed.password, database_url)
    for path in sorted(set(paths)):
        try:
            findings.extend(scan_file(root, path, env_values=env_values, payload=path in deploy_set))
        except (OSError, ValueError):
            findings.append(Finding(str(path), 0, "unreadable"))
    return sorted(set(findings), key=lambda item: (item.path, item.line, item.rule))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--source", action="store_true")
    parser.add_argument("--build", action="store_true")
    parser.add_argument("--deploy-payload", action="store_true")
    parser.add_argument("--env-file", type=Path)
    parser.add_argument("--artifact", action="append", default=[], type=Path)
    args = parser.parse_args()
    source = args.source or not (args.build or args.artifact or args.deploy_payload)
    extra_values = env_file_values(args.env_file) if args.env_file else ()
    findings = run(
        root=ROOT, source=source, build=args.build,
        artifacts=args.artifact, deploy=args.deploy_payload, extra_values=extra_values,
    )
    for finding in findings:
        file_id = hashlib.sha256(finding.path.encode()).hexdigest()[:12]
        print(f"file#{file_id}:{finding.line}: {finding.rule}")
    if findings:
        raise SystemExit(f"secret exposure gate failed: {len(findings)} finding(s); values withheld")
    print("secret exposure gate OK")


if __name__ == "__main__":
    try:
        main()
    except (subprocess.CalledProcessError, OSError, ValueError):
        raise SystemExit("secret exposure gate failed: inventory or env file invalid") from None
