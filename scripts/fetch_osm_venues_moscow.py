#!/usr/bin/env python3
"""Fetch Moscow event-venue candidates from OpenStreetMap (Overpass).

Splits Moscow into bbox tiles and queries lz4 Overpass in small batches
(more reliable than one huge area query).

Usage:
  python scripts/fetch_osm_venues_moscow.py --out /tmp/osm_venues_raw.json
"""

from __future__ import annotations

import argparse
import json
import sys
import time
import urllib.error
import urllib.parse
import urllib.request

# Moscow approximate bbox (south, west, north, east)
BBOX = (55.489, 37.319, 55.958, 37.967)
GRID = 3  # 3x3 tiles

OVERPASS_ENDPOINTS = [
    "https://lz4.overpass-api.de/api/interpreter",
    "https://overpass-api.de/api/interpreter",
    "https://overpass.kumi.systems/api/interpreter",
]

TAG_FILTERS = [
    '["amenity"="conference_centre"]',
    '["amenity"="events_venue"]',
    '["amenity"="music_venue"]',
    '["amenity"="theatre"]',
    '["amenity"="arts_centre"]',
    '["amenity"="community_centre"]',
    '["amenity"="cinema"]',
    '["amenity"="nightclub"]',
    '["tourism"="museum"]["name"]',
    '["tourism"="gallery"]["name"]',
    '["leisure"="stadium"]["name"]',
    '["leisure"="sports_centre"]["name"]',
]


def _tiles() -> list[tuple[float, float, float, float]]:
    s, w, n, e = BBOX
    tiles = []
    for i in range(GRID):
        for j in range(GRID):
            south = s + (n - s) * i / GRID
            north = s + (n - s) * (i + 1) / GRID
            west = w + (e - w) * j / GRID
            east = w + (e - w) * (j + 1) / GRID
            tiles.append((south, west, north, east))
    return tiles


def _coords(el: dict) -> tuple[float | None, float | None]:
    if "lat" in el and "lon" in el:
        return float(el["lat"]), float(el["lon"])
    center = el.get("center") or {}
    if "lat" in center and "lon" in center:
        return float(center["lat"]), float(center["lon"])
    return None, None


def _address(tags: dict, lat: float | None, lon: float | None) -> str:
    if tags.get("addr:full"):
        return str(tags["addr:full"]).strip()
    street = tags.get("addr:street") or ""
    house = tags.get("addr:housenumber") or ""
    city = tags.get("addr:city") or ""
    parts = [p for p in (street, house) if p]
    address = ", ".join(parts).strip(", ")
    if city and city not in address:
        address = f"{address}, {city}" if address else city
    if address:
        return address
    if lat is not None and lon is not None:
        return f"{lat:.5f},{lon:.5f}"
    return ""


def _quality(tags: dict, address: str, website: str) -> int:
    score = 0
    if website:
        score += 40
    if address and any(c.isalpha() for c in address):
        score += 30
    else:
        score += 5
    amenity = tags.get("amenity") or ""
    tourism = tags.get("tourism") or ""
    leisure = tags.get("leisure") or ""
    if amenity in {"conference_centre", "events_venue", "theatre", "arts_centre", "music_venue"}:
        score += 25
    elif amenity in {"community_centre", "cinema", "nightclub"}:
        score += 15
    elif tourism in {"museum", "gallery"}:
        score += 12
    elif leisure in {"stadium", "sports_centre"}:
        score += 10
    if tags.get("capacity") or tags.get("seats"):
        score += 8
    return score


def parse_elements(elements: list) -> list[dict]:
    rows: list[dict] = []
    for el in elements:
        tags = el.get("tags") or {}
        name = tags.get("name") or tags.get("name:ru")
        if not name:
            continue
        lat, lon = _coords(el)
        address = _address(tags, lat, lon)
        if not address:
            continue
        osm_type = el.get("type")
        osm_id = el.get("id")
        osm_url = f"https://www.openstreetmap.org/{osm_type}/{osm_id}"
        capacity_raw = tags.get("capacity") or tags.get("seats") or ""
        capacity = int(capacity_raw) if str(capacity_raw).isdigit() else None
        website = tags.get("website") or tags.get("contact:website") or ""
        rows.append(
            {
                "name": name.strip(),
                "address": address,
                "district": tags.get("addr:suburb") or tags.get("addr:district") or "",
                "metro": tags.get("subway")
                or tags.get("nearby_station")
                or tags.get("addr:subway")
                or "",
                "capacity": capacity,
                "description": tags.get("description") or tags.get("note") or "",
                "source_url": website or osm_url,
                "attribution": "openstreetmap",
                "osm_url": osm_url,
                "lat": lat,
                "lon": lon,
                "quality": _quality(tags, address, website),
                "osm_tags": {
                    k: tags[k]
                    for k in sorted(tags)
                    if k.startswith(("amenity", "tourism", "leisure", "building", "addr", "club"))
                },
            }
        )
    return rows


def _query(tile: tuple[float, float, float, float], filters: list[str]) -> str:
    s, w, n, e = tile
    lines = [f"  nwr{f}({s},{w},{n},{e});" for f in filters]
    inner = "\n".join(lines)
    return f"[out:json][timeout:60];\n(\n{inner}\n);\nout center tags;\n"


def _post_overpass(endpoint: str, query: str) -> dict:
    body = urllib.parse.urlencode({"data": query}).encode()
    req = urllib.request.Request(endpoint, data=body, method="POST")
    req.add_header("Content-Type", "application/x-www-form-urlencoded")
    req.add_header("User-Agent", "booker-venue-curator/1.0 (bukergo.ru; research)")
    with urllib.request.urlopen(req, timeout=90) as resp:
        return json.load(resp)


def fetch_query(query: str) -> list:
    last_err: Exception | None = None
    for endpoint in OVERPASS_ENDPOINTS:
        try:
            data = _post_overpass(endpoint, query)
            return data.get("elements") or []
        except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, OSError) as exc:
            last_err = exc
            print(f"overpass fail {endpoint}: {exc}", file=sys.stderr)
            time.sleep(1.5)
    raise RuntimeError(f"All Overpass endpoints failed: {last_err}")


# Amenity/tourism groups to keep each request small.
FILTER_GROUPS = [
    TAG_FILTERS[0:4],
    TAG_FILTERS[4:8],
    TAG_FILTERS[8:12],
]


def fetch() -> dict:
    by_osm: dict[str, dict] = {}
    tiles = _tiles()
    total_jobs = len(tiles) * len(FILTER_GROUPS)
    job = 0
    for tile in tiles:
        for group in FILTER_GROUPS:
            job += 1
            print(f"job {job}/{total_jobs} tile={tile} filters={len(group)}", file=sys.stderr)
            try:
                elements = fetch_query(_query(tile, group))
            except RuntimeError as exc:
                print(f"skip failed job: {exc}", file=sys.stderr)
                continue
            for row in parse_elements(elements):
                key = row.get("osm_url") or f"{row['name']}|{row['address']}"
                prev = by_osm.get(key)
                if prev is None or int(row.get("quality") or 0) > int(prev.get("quality") or 0):
                    by_osm[key] = row
            time.sleep(0.4)
    rows = list(by_osm.values())
    rows.sort(key=lambda r: (-int(r.get("quality") or 0), r["name"].lower()))
    return {"count": len(rows), "source": "openstreetmap", "venues": rows}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=str, default="", help="Write JSON to file instead of stdout")
    args = parser.parse_args()
    payload = fetch()
    text = json.dumps(payload, ensure_ascii=False, indent=2) + "\n"
    if args.out:
        with open(args.out, "w", encoding="utf-8") as f:
            f.write(text)
        print(f"wrote {payload['count']} venues -> {args.out}", file=sys.stderr)
    else:
        sys.stdout.write(text)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
