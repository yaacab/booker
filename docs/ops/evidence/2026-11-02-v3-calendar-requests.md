# V3 — Calendar & Requests (thin slice)

**Date:** 2026-11-02  
**Branch:** `feat/v3-calendar-requests`  
**Worktree:** `/home/art67/booker-worktrees/v3-calendar-requests`  
**Base:** `0bd7aa0`

## Scope

1. `DELETE /slots/{slot_id}` — only unused `open` slots; blocks held/confirmed/busy and active deals.
2. `slot_is_bookable()` — open + not masked by vacation/iCal busy overlays.
3. `quick-request` and `create_offer` reject non-bookable slots (409).
4. Cabinet calendar: delete open slots from overview when writer.

## Tests / review

- `test_slot_delete_and_bookable.py` + vacation/buffers/cabinet/hold_race: **15 PASS**
- Focused delete/bookable: **4 PASS**
- Ruff: PASS
- Independent security review: **PASS**
- Merge / push / production: NO-GO

Scores unchanged: FULL 59,00% / MVP 56,00% / Design 15,00%.
