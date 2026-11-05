# Scene 01 v5: web-only live overlay

Authorization: owner asked on 2026-10-15 to publish the current design and working site on bukergo.ru.

Scope: existing production Next.js app, replacing only app/page.tsx and adding components/Scene01LiveHome.tsx + app/scene01-live.css. Uses the first scene from outputs/animation-preview-20261014/source/src/App.tsx; all registration, catalog, event submission and deal routes remain the running production implementation. Role cards navigate to the real registration screen. No mock authentication, catalog or submission is included.

Prepare in a new /opt/booker/web-releases directory using an on-host copy of the current web sources. Preserve the existing source and .next build. Reuse the existing node_modules read-only. Build and inspect on a loopback-only port before switching only booker-web.service via one systemd drop-in. Save the prior unit configuration, full baseline source hashes and the overlay hashes. Recheck source and unit hashes at switch. Rollback removes only the new drop-in and restarts the original web unit; existing API, database, nginx and payment configuration are outside scope.

This release does not deploy candidate 0771cd7, new API migrations or the remaining prototype scenes. It is not proof of full CORE, legal readiness or live payments.

## Continuity and history-back fix, 2026-10-15

The owner reported that role selection opened the old black/lime registration and Safari Back could restore a blank scene. `Scene01LiveHome` now uses `apps/web/lib/scene01Recovery.ts`: pageshow remounts a cached scene; a session marker returns fresh documents to the role cards; storage denial has an in-memory fallback; replay clears the marker. Seven regression cases run through the normal web unit discovery.

`scene01-continuity.css` supplies a single cream/paper/ink/gold palette to the existing application. A layered color override takes precedence over saved legacy editions, retaining the real form fields and API calls. `layout-updates.json` lists the three exact transformations for the fingerprinted production layout: import the stylesheet, add the cream-theme attribute, set browser theme color. Layout or source drift blocks preparation.

The continuity release additionally copies the recovery helper and global palette into a new isolated copy of the currently running frontend. Existing API/data are unchanged. Preview checks must include all role links, repeated Back/Forward, replay, 320/390 desktop views, field/consent visibility and saved Black Edition. Safari screenshots from the owner are bug evidence; Chromium preview testing does not claim a real iPhone retest.
