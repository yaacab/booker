# Authz / IDOR expand (LOCAL)

Added regressions in `tests/test_authz_regressions.py`:

- outsider cannot GET deal-room
- outsider cannot GET foreign org
- outsider cannot revoke foreign shortlist
- supplier cannot invite into customer org

Does **not** close T11/S07 staging isolation. Scores unchanged.
