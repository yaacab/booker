# Moscow district discovery map

The `/search?kind=venue` page is a noindex research selection separate from booking. It uses the 300 source-attributed records in `moscow_performance_venues_research.json`. No calendar or ownership status is invented, and no production records are deleted. The artist catalog defaults to artists; venue research is an explicit alternate entry.

## Geographic sources

- Boundaries: OpenStreetMap contributors, ODbL 1.0, <https://www.openstreetmap.org/copyright>. Overpass area query: Moscow (`name=Москва`, `boundary=administrative`, `admin_level=4`), member-area relations with `boundary=administrative`, `admin_level=8`, `out geom`. Downloaded 11 September 2026; the source snapshot reports 31 May 2026, which is shown in the interface. 132 relations are included.
- Coordinates: each existing SpeedRent source card's `data-coords` attribute, in latitude/longitude order. Page encoding differences are handled without changing coordinate digits. No geocoding guesses or metro-to-district heuristics are used.
- `data/moscow_venue_districts.json` retains individual source URLs and the boundary timestamp. Records without a polygon match remain in the all-district selection and are labelled as needing clarification.
- `apps/web/lib/moscowDistrictGeometry.json` is the derived boundary display dataset, licensed under ODbL 1.0. Dataset source and license are embedded and attributed in the visible map. The map uses a Mercator projection; it is a presentation map, not a routing or availability map.

## Reproduction and checks

Save the Overpass JSON and source-coordinate list, then run `python scripts/build_moscow_district_map.py OSM_JSON COORDINATES_JSON`. The builder joins ways into closed outer/inner rings and rejects incomplete boundaries or ambiguous multiple district matches. Point-in-polygon uses full precision geometry, including holes. Only display rings are simplified, with tolerance 0.00016 degrees. Do not classify addresses against simplified display paths.

The browser check verifies real photos, all 132 paths, district dropdown and polygon pointer selection, gallery selection, budget empty state, noindex metadata, and no horizontal overflow on desktop/tablet/mobile in both editions. A district dropdown provides the equivalent keyboard/touch selection; hover previews the name and count without changing the chosen filter.

Cards show 24 items initially, with more loaded on request. Galleries render their thumbnails only when expanded. External photos remain with attribution and direct source links; no copies are made or associated with unrelated existing venue profiles.
