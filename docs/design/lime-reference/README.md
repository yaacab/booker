# Lime glass reference implementation

Base: `origin/feat/master-plan-execution` at `915d606`. Branch: `feat/lime-puzzle-reference`.

Visual scope: light silver/forest/lime theme for shared chrome, forms and role
workspaces; homepage reference composition with three independent photo puzzle
buttons. No API, booking, auth, payment, deployment or DNS changes.

Interaction: click/tap toggles one piece; selecting another releases the first;
Space/Enter use native button behaviour; Escape clears within the puzzle group.
Desktop lift 20px, mobile lift 12px, subtle scale/shadow. Reduced-motion removes
movement and marks selection by outline. Selection is ephemeral, not a booking.

Artwork: generated using the built-in image generator, copied to
`apps/web/public/design/puzzle-{dj,venue,photographer}.png`. The images are
illustrative category art and never represent real supplier profiles.
Prompt family: isolated front-facing rounded square photographic jigsaw tile,
left circular socket/right tab, transparent surroundings, thin clear glass lime
rim, warm editorial daylight, no labels/logos; subjects are DJ at mixing console,
sunlit industrial event loft and photographer holding a camera. Text is real HTML.
Assets are intentionally newly illustrated, not pixel-identical people from the mock.

Validation: `npm run lint`, `npm run test:unit` (36 passed), `npm run build`.
Browser checks: desktop 1363x936, mobile viewport in a 390x844 same-origin iframe,
three images loaded, click/tap/switch/deselect, Space/Escape, artist/venue search
toggle. CLI E2E file updated but not executed; reduced-motion browser emulation and
authenticated backend flows remain review/CI checks. No fabricated passing results.

Preview uses the existing Next runtime with `sites-preview`, not a production deploy.
Security changes in the separate original worktree were left untouched.
