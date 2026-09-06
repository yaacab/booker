# Immersive Buker redesign — work in progress

final result: blocked

## Scope and source

- Branch: `feat/immersive-buker-design`, base `20b0051`.
- Visual direction: uploaded `EE561C12-34C4-4799-A568-E49380CDB4BD.mp4`: dark stage, cyan/violet/pink refractive materials. This is an art-direction adaptation, not a pixel-perfect clone.
- Existing production home inspected in the cloud browser before editing. Its light palette and technical hero copy were replaced locally; no production deployment performed.
- Generated hero: `apps/web/public/design/puzzle-hero.webp`, 1024 × 1024, approximately 89 KB. Built-in ImageGen prompt: six beveled glass jigsaw pieces in an exploded assembly on near-black, cyan/violet/pink refraction, no text or UI. Original PNG retained in the scratch generated_images directory.

## Checks

- TypeScript `npm run lint`: passed.
- `git diff --check`: passed before final documentation.
- Unit tests: **35 passed**, 0 failed, 0 skipped. Includes five new design regression tests and puzzle assembly/release test.
- Production build: passed, 36 static pages. Home First Load JS 113 kB (build estimate, not Lighthouse).
- Local preview is running through `sites-preview`; browser opening was blocked by the Cloud browser URL policy. No workaround or alternate browser runner used.
- Implementation screenshot: unavailable. Viewport/density comparison and combined reference/render evidence: not available.
- Fonts, layout rhythm, color contrast, asset integration, copy, mobile responsiveness, and authenticated role screens: require browser verification.
- Primary interactions and console errors on local implementation: not yet verified.

## Remaining acceptance work

1. Open the preview in an authorized browser environment and run E2E. `apps/web/e2e/immersive-design.spec.ts` adds 390/1440 checks, search toggle, image load, overflow, reduced-motion and screenshot capture. These E2E tests have NOT been run.
2. Compare reference and rendered home together; capture desktop and 390px mobile evidence.
3. Test artist/venue search, form date selection, navigation and flag-on/off Event Studio.
4. Inspect all three authenticated cabinets, legacy wizard and Deal Room for hard-coded light surfaces under the new dark tokens; fix contrast before accepting the global theme.
5. Test actual puzzle assembly and reduced-motion state; current change is 2.5D SVG animation, not a real-time 3D/disintegration engine.
6. Narrow the design scope or amend the product contract explicitly before introducing a true 3D feature. Existing no-3D domain restriction was not removed.
7. Keep review in draft until visual evidence exists. No master merge or production deploy without separate approval.

## Rollback

Changes are isolated in the design branch. Cabinet and studio branches were integrated by cherry-pick. Revert the redesign commits to restore home/layout/studio styles and remove the new stylesheet/asset; no database or API changes are involved. Disabling the studio flag alone restores the classic wizard, NOT the global theme. Home studio links explicitly opt in via query; default-off remains unchanged.

## Source and comparison evidence

- Source visual truth: `../upload/EE561C12-34C4-4799-A568-E49380CDB4BD.mp4`, 512×910 recorded screen; extracted images `../video-frames/t-5.jpg`, `t-9.jpg`, `t-13.jpg`.
- Implementation screenshot path: unavailable.
- Planned viewports: 1440×900 and 390×900. Actual viewport and density normalization: not captured.
- Planned states: anonymous home/search/studio plus authenticated customer/performer/venue and Deal Room.
- Full-view and focused-region comparisons: not performed. No fabricated comparison history; code review/build success is not visual QA.
- Fonts: existing local Manrope retained; wrapping and optical balance await render.
- Spacing/layout: responsive grids reviewed in source, not in screenshot.
- Colors: primary text tokens numerically meet 4.5:1 in unit tests; this is not a complete accessibility audit.
- Images: generated asset inspected separately, browser crop/sharpness remains unchecked.
- Copy: pilot warning retained; reference portraits and fake venue photo removed, honest initials used while API adapter has no media.
- Browser interactions and console errors: not checked because implementation could not open.

## Independent code review fixes

1. Added separate dark `brand-hover` token to prevent white button labels on pale lilac hover.
2. Corrected time-editor input specificity to override legacy white background.
3. Restored numbered stage spans when compact rail hides text labels.
4. Studio uses intrinsic grid to accommodate expanded editors; unique SVG gradient IDs and reduced-motion assembly/release feedback.
5. Role-specific dark cabinets preserve existing permissions, APIs and workflows. No live payment, deployment, or server change.
