# A1 — Staging launcher finish (LOCAL)

**SHA base:** `c32fd89` + this commit  
**Level:** LOCAL only — not T10/T12 staging score  
**Docker/staging-up:** not run (agent without Docker+secrets); unit + dry-run only

## Gaps closed

| Gap | Mechanism |
| --- | --- |
| PID ownership + clean stop | `pid_owned_by_booker_staging()` via `/proc/<pid>/cmdline`; staging-up/down refuse foreign PIDs |
| Refuse unknown `.next` | `/tmp/booker-staging/web-build.sha` must match `git rev-parse HEAD` |
| Compose secret redaction | `redact_secrets()` + `--redact-file`; only redacted config logged |
| Path/symlink checks | uploads + env-file allowlist; symlink resolve escape → FAIL |
| Port conflict | bind without SO_REUSEADDR; never kill foreign listeners |
| No seed/migrate without preflight | unchanged order: preflight PASS → compose → migrate → seed |
| Web build ↔ SHA | stamp written after build under `/tmp/booker-staging/` |

## Tests

`python3 -m pytest infra/test_staging_preflight.py -q` → **21 PASS** (was 13).

## Explicit non-claims

- No Infrastructure GO / VPS purchase  
- No staging E2E score  
- Scores FULL/MVP/Design unchanged  
