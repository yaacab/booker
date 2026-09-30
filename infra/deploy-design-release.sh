#!/usr/bin/env bash
# Read-only exact-commit release preflight. Never SSHs or deploys.
set -euo pipefail
export GIT_OPTIONAL_LOCKS=0

usage() {
  cat <<'HELP'
Usage: bash infra/deploy-design-release.sh FULL_COMMIT [--base FULL_COMMIT] [--host]

Default: inspect the committed release in this repository; do not write files.
--base: compare with an independently verified production commit (never guess it).
--host: additionally inspect the existing /opt/booker services on the VPS itself.

This command has no execute/deploy mode and makes no network connections.
It never includes working-tree changes. See docs/ops/DESIGN_RELEASE_RUNBOOK.md.
Exit 0 = checks completed, NOT deployment approval or production readiness.
Exit 2 = invalid input. Exit 3 = blocked runtime prerequisite.
HELP
}

die() { printf 'BLOCKED: %s\n' "$*" >&2; exit 3; }
[[ $# -gt 0 ]] || { usage; exit 2; }
[[ "$1" != --help && "$1" != -h ]] || { usage; exit 0; }
target="$1"
shift
base=''
host_check=0
while [[ $# -gt 0 ]]; do
  case "$1" in
    --base)
      [[ $# -ge 2 && -z "$base" ]] || { usage; exit 2; }
      base="$2"
      shift 2
      ;;
    --host) host_check=1; shift ;;
    *) usage; exit 2 ;;
  esac
done
repo="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")/.." && pwd -P)"
cd -- "$repo"
for revision in "$target" "$base"; do
  [[ -n "$revision" ]] || continue
  [[ "$revision" =~ ^([0-9a-f]{40}|[0-9a-f]{64})$ ]] || {
    printf 'Full lowercase commit object ID required: %s\n' "$revision" >&2
    exit 2
  }
  [[ "$(git cat-file -t "$revision" 2>/dev/null)" == commit ]] || {
    printf 'Commit object unavailable: %s\n' "$revision" >&2
    exit 2
  }
done
printf 'Release commit: %s\n' "$target"
printf 'Working-tree changes are excluded from the release archive.\n'
git status --short --untracked-files=normal
for path in apps/web/package.json apps/web/package-lock.json apps/api/pyproject.toml; do
  git cat-file -e "$target:$path" || die "release is missing $path"
done
if git ls-tree -r "$target" | awk '$1 == "120000" || $1 == "160000" {found=1} END {exit !found}'; then
  die 'archive contains symlinks or submodules; review a separate extraction procedure'
fi
if [[ -n "$base" ]]; then
  printf '\nDiff from supplied production commit %s:\n' "$base"
  git diff --stat "$base" "$target"
  printf '\nBackend, schema, dependency and infrastructure review gate:\n'
  git diff --name-status "$base" "$target" -- apps/api infra \
    apps/web/package.json apps/web/package-lock.json apps/web/next.config.ts
else
  printf '\nProduction baseline UNKNOWN. Live source comparison is required.\n'
fi
printf '\nCommit sanity: PASS. Production readiness: NOT ESTABLISHED.\n'
[[ "$host_check" == 1 ]] || exit 0

for cmd in systemctl systemd-run python3 curl df stat sqlite3 node npm \
  flock runuser tar sha256sum ss; do
  command -v "$cmd" >/dev/null || die "required host command unavailable: $cmd"
done
[[ -d /opt/booker && ! -L /opt/booker ]] || die '/opt/booker is absent or a symlink'
[[ -d /opt/booker/apps/web && ! -L /opt/booker/apps/web ]] || die 'unexpected live web layout'
[[ -d /opt/booker/apps/api && ! -L /opt/booker/apps/api ]] || die 'unexpected live API layout'
[[ -s /opt/booker/apps/web/.next/BUILD_ID ]] || die 'live Next BUILD_ID is missing'
[[ -f /opt/booker/data/booker.db ]] || die 'expected SQLite pilot DB is absent'
[[ -x /opt/booker/.venv/bin/python ]] || die 'live Python virtualenv is absent'
for service in booker-web booker-api; do
  systemctl is-active --quiet "$service" || die "$service is not active"
  [[ "$(systemctl show "$service" -p User --value)" == booker ]] || die "$service has an unexpected user"
  [[ "$(systemctl show "$service" -p Group --value)" == booker ]] || die "$service has an unexpected group"
  expected_directory="/opt/booker/apps/${service#booker-}"
  [[ "$(systemctl show "$service" -p WorkingDirectory --value)" == "$expected_directory" ]] || die "$service has an unexpected working directory"
  printf '\n%s runtime paths (environment values omitted):\n' "$service"
  systemctl show "$service" -p WorkingDirectory -p User -p Group -p MainPID -p FragmentPath -p DropInPaths
done
api_pid="$(systemctl show booker-api -p MainPID --value)"
web_pid="$(systemctl show booker-web -p MainPID --value)"
python3 - "$target" "$api_pid" "$web_pid" <<'PY'
import os
from pathlib import Path
import subprocess
import sys

target, api_pid, web_pid = sys.argv[1:]
def stop(message):
    print('BLOCKED: ' + message, file=sys.stderr)
    raise SystemExit(3)

def environment(pid):
    if not pid.isdigit() or int(pid) <= 1:
        stop('unexpected service PID')
    try:
        return dict(item.split(b'=', 1) for item in Path('/proc', pid, 'environ').read_bytes().split(b'\0') if b'=' in item)
    except OSError:
        stop('cannot privately read service environment; run host preflight with sufficient access')

api = environment(api_pid)
web = environment(web_pid)
if api.get(b'BOOKER_DATABASE_URL') != b'sqlite:////opt/booker/data/booker.db':
    stop('effective database is not the documented SQLite pilot; actual value withheld')
if api.get(b'BOOKER_UPLOAD_DIR') != b'/opt/booker/data/uploads':
    stop('effective uploads path needs a separate persistence review; actual value withheld')
for key, wanted in {
    b'BOOKER_INTERNAL_API_URL': b'http://127.0.0.1:8030',
    b'NEXT_PUBLIC_API_URL': b'/api',
    b'NEXT_PUBLIC_SITE_URL': b'https://bukergo.ru',
}.items():
    if web.get(key) != wanted:
        stop('unexpected web setting ' + key.decode() + '; value withheld')
print('Effective DB, uploads and web endpoints match the documented pilot.')
print('Build-time feature flags still require confirmation from the previous build record.')

# Compare the entire tracked API tree without executing application code or reading DB rows.
tree = subprocess.check_output(['git', 'ls-tree', '-rz', target, '--', 'apps/api'])
expected = {}
for record in tree.split(b'\0'):
    if not record:
        continue
    metadata, name = record.split(b'\t', 1)
    expected[os.fsdecode(name)] = metadata.split()[2].decode()
different = []
for name, oid in expected.items():
    live = Path('/opt/booker', name)
    if live.is_symlink() or not live.is_file():
        different.append(('missing/type', name))
    elif subprocess.check_output(['git', 'hash-object', '--no-filters', '--', str(live)], text=True).strip() != oid:
        different.append(('changed', name))
ignored_dirs = {'.git', '.venv', '__pycache__', '.pytest_cache', '.ruff_cache', 'data'}
for root, directories, files in os.walk('/opt/booker/apps/api', followlinks=False):
    for name in directories[:]:
        path = Path(root, name)
        if path.is_symlink():
            stop('unexpected symlink in live API tree; review persistence before any directory switch')
    directories[:] = [name for name in directories if name not in ignored_dirs]
    for name in files:
        relative = str(Path(root, name).relative_to('/opt/booker'))
        if relative not in expected and not name.endswith(('.pyc', '.pyo')):
            different.append(('live-only', relative))
print('\nLive API comparison against release (review every difference):')
for state, name in different:
    print(state + '\t' + name)
if not different:
    print('Identical tracked API content; no additional live API files found.')
else:
    print('Companion backend gate REQUIRED; no code/schema compatibility inferred.')
PY
printf '\nDisk capacity (operator must budget source, dependencies, build, rollback and DB copies):\n'
df -h /opt/booker /var/backups
printf '\nCurrent build ID: '
cat /opt/booker/apps/web/.next/BUILD_ID
printf '\nRead-only service health:\n'
curl --fail --silent --show-error --max-time 10 --output /dev/null http://127.0.0.1:8030/health
curl --fail --silent --show-error --max-time 15 --output /dev/null http://127.0.0.1:3030/
printf 'Host preflight: PASS. No staging, backups, build or switch performed.\n'
printf 'Production readiness remains conditional on every runbook gate.\n'
