# Design system audit — BookerGo (2026-10-15)

**Branch:** `cursor/design-system-cbf8`  
**Status:** prep for owner D02 / motion GO — **no web visual ship** without approval  
**Scores:** Design scale remains **15** until D02 criteria met

## Sources audited

| Source | Path / URL | Finding |
| --- | --- | --- |
| Figma detail progress | `FIGMA_DETAIL_PROGRESS_2026-09-30.md` | Home / Choice / Event Studio step1 + states exist; not full 93-task registry |
| Screen atlas | `SCREEN_REFERENCE_ATLAS.md` + `.html` | 75 families mapped; composition language defined |
| Motion v2 | `MOTION_PREVIEW_SLOT_FRAME_V2_UNAPPROVED.md` | **UNAPPROVED**; must not integrate to `apps/web` |
| Motion direction | `MOTION_DIRECTION_2026-09-30.md` | Direction only («Рамка слота») |
| Route audit | `ROUTE_AUDIT_2026-09-30.md` | Route ↔ screen coverage gaps remain |
| Live CSS | `apps/web/app/globals.css` | Light paper theme; atlas dark glass tokens not yet unified |

## Token extract (canonical proposal)

See `tokens/booker-tokens.css` — dual surfaces (atlas dark + document light) as CSS variables only.  
**Not imported** into production layouts on this branch until D02.

## State matrix (minimum for D02)

| State | Required on Choice / Catalog / Deal | Atlas coverage | Gap |
| --- | --- | --- | --- |
| Loading | skeleton + retain filters | Choice desktop/mobile | Home loading thin |
| Empty | message + next action | Choice | Catalog empty needs API copy |
| Error / retry | retry CTA | Choice | Deal SSE reconnect UI |
| Conflict | alternatives CTA | Choice | Calendar conflict copy |
| Reduced motion | static frame | Home + motion preview | Product pages not verified |
| No access / 404 | honest empty | partial | Guest shortlist expired |
| Hold / offer expired | explicit | atlas note | UI polish |

## Motion approval packet

Owner must choose one for «Рамка слота» v2:

1. **Approve** → integrate tokens + transform-only motion ≤480ms + reduced-motion fallback  
2. **Reject** → keep static hero; archive UNAPPROVED preview  
3. **Revise** → list frame/timing/color notes; stay UNAPPROVED

Checklist: `D02_MOTION_APPROVAL_PACKET.md`

## Explicit non-actions

- No merge into product candidate without D02 GO  
- No claim Design score >15  
- No live photo / price / availability fiction in mocks  
