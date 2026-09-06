# Lime reference QA — 2026-09-06

Source visual truth: `docs/design/lime-reference/source.jpeg` (1487x1058).
Browser-rendered evidence: `docs/design/lime-reference/desktop.jpg`,
`mobile-frame.jpg`, `selected.jpg`; paths relative to `docs/design/lime-reference/`.
Comparison: `docs/design/lime-reference/comparison.png`.
Desktop CSS viewport reported 1363x936, stored browser capture 1348x926;
source scaled proportionately to 1363px wide, white padding below the shorter
implementation. Both captures normalized to 1363px wide. No source crop.
Mobile CSS viewport 390x844 in a same-origin iframe, cropped from a 1363x936 capture,
not a physical-device test. Main route `/`, unauthenticated, light theme.

## Comparison history

1. P1: legacy global button backdrop-filter and shadow created rectangular panels
   around transparent puzzle assets. Reset backdrop-filter and box-shadow for hero
   buttons, preserving alpha-aware drop-shadow. Post-fix desktop evidence shows
   jigsaw silhouettes without rectangular frames.
2. P2: excessive hero height pushed CTA below initial viewport. Reduced heading
   size/line-height and placed desktop description beside heading rather than adding
   another full row. Final desktop/selected evidence shows CTA within viewport.
3. P2: login grouped with central nav unlike reference. Separated unauthenticated
   login while keeping authenticated workspace/notification links intact. Final
   selected evidence shows central glass navigation and separate login.

## Fidelity surfaces

- Typography: local Manrope, bold three-line slogan, matching text hierarchy;
  font-face weight range extended to 800. Not the exact unidentified source font.
- Layout: left legend, three adjacent photo puzzle buttons, centered rounded CTA;
  mobile keeps all three adjacent and replaces legend with accessible role buttons.
- Colors: silver-white canvas, forest text, translucent lime CTA/glass photo edges.
  Ink/muted/link token contrast is covered by unit tests. Semantic error/success
  colors remain distinguishable; no black-purple theme in the changed visual layer.
- Images: three independent generated raster illustrations with alpha, loaded and
  sharp in browser. Human/venue subjects are not identical to the mock; decorative
  offscreen glass fragments are omitted. These are illustrative category assets,
  not verified or available supplier profiles. This is a reference-led implementation,
  not a pixel-identical screenshot reproduction.
- Copy: approved slogan retained verbatim. Labels are HTML, not baked into images.
  No fabricated prices, availability, ratings or financial guarantees.

Focused comparison: source and implementation headline/puzzle-label regions
inspected at full-size captures, in addition to the normalized full-view comparison.
Reference supporting labels are small; implementation uses dark translucent label
backplates for contrast, and hides secondary captions on narrow mobile screens.

## Behaviour and validation

- Browser: click raises a piece; second click deselects; another selection releases
  prior piece. Space activates and Escape clears. Mobile photographer selection
  checked in 390px iframe. No horizontal desktop overflow.
- Browser: artist/venue search toggle still exposes the correct fields.
- Browser logs: inspected 50-error window; errors shown are browser-extension
  metadata messages, not application errors.
- TypeScript lint passed; 36 unit tests passed; production build passed.
- E2E spec updated for click/switch/repeat/keyboard/reduced-motion. Full Playwright
  CLI suite was not executed. Reduced-motion CSS is present and checked statically,
  but real browser reduced-motion emulation remains a CI check.
- Authenticated cabinets and backend transaction flows were not exercised. Shared
  palette changes compile, but this report does not certify their end-to-end release.

## Follow-up polish

P3: exact art-director photo selection, background glass decoration and optical
font matching can be refined after owner review. Core interaction and light palette
are ready for that review; this is not approval for production deployment.

final result: passed
