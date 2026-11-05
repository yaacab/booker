# CORE mobile hold — 05.10.2026

Base: 4f7e4bfc4cd338dba89b4dd56d4b2aa16633d844. At390px both acknowledgements succeeded but desktop hold was hidden and mobile action repeated acknowledgement. Fix: customer+Negotiation+both current quote acknowledgements selects hold through existing authoritative API.

E08 uses mobile actions and opens offer sheet for hold expiry. Local frontend + real private-stage test API: 1 PASS/26.5s, /tmp/booker-mobile-hold-fix-v4.log. Temporary Playwright request forwarding avoided differing local origin without changing stage CORS; responses are real, not mocked. Functional proof only, not deployed frontend/CORS acceptance. TypeScript/diff-check PASS. Prior probe reproduced missing hold; v3 reached hold200 then failed on desktop-only indicator assertion, corrected to mobile sheet.

Not deployed. Next exact commit CI, rebuilt private-stage frontend, full mobile/operator and rollback acceptance. CORE80/ACCESS0/FULL59/MVP56/DESIGN15 unchanged.
