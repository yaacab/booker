# Scene 01 v5: web-only live overlay

Authorization: owner asked on 2026-10-15 to publish the current design and working site on bukergo.ru.

Scope: existing production Next.js app, replacing only app/page.tsx and adding components/Scene01LiveHome.tsx + app/scene01-live.css. Uses the first scene from outputs/animation-preview-20261014/source/src/App.tsx; all registration, catalog, event submission and deal routes remain the running production implementation. Role cards navigate to the real registration screen. No mock authentication, catalog or submission is included.

Prepare in a new /opt/booker/web-releases directory using an on-host copy of the current web sources. Preserve the existing source and .next build. Reuse the existing node_modules read-only. Build and inspect on a loopback-only port before switching only booker-web.service via one systemd drop-in. Save the prior unit configuration, full baseline source hashes and the overlay hashes. Recheck source and unit hashes at switch. Rollback removes only the new drop-in and restarts the original web unit; existing API, database, nginx and payment configuration are outside scope.

This release does not deploy candidate 0771cd7, new API migrations or the remaining prototype scenes. It is not proof of full CORE, legal readiness or live payments.
