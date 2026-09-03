#!/usr/bin/env python3
"""Fetch raw Moscow event-venue candidates from OpenStreetMap (Overpass).

Usage:
  python scripts/fetch_osm_venues_moscow.py > /tmp/osm_venues_raw.json

Curate results into data/moscow_venues_open.json — do not import the raw dump
into production seed without review.
"""

from __future__ import annotations

import json
import sys
import urllib.parse
import urllib.request

OVERPASS = "https://overpass-api.de/api/interpreter"

QUERY = """
[out:json][timeout:90];
area["name"="Москва"]["admin_level"="4"]->.a;
(
  node["amenity"="conference_centre"](area.a);
  way["amenity"="conference_centre"](area.a);
  node["amenity"="events_venue"](area.a);
  way["amenity"="events_venue"](area.a);
  node["tourism"="attraction"]["name"](area.a);
  way["building"="civic"]["name"](area.a);
);
out center tags 80;
"""


def main() -> int:
    body = urllib.parse.urlencode({"data": QUERY}).encode()
    req = urllib.request.Request(OVERPASS, data=body, method="POST")
    req.add_header("Content-Type", "application/x-www-form-urlencoded")
    req.add_header("User-Agent", "booker-venue-curator/1.0 (bukergo.ru; research)")
    with urllib.request.urlopen(req, timeout=120) as resp:
        data = json.load(resp)
    rows = []
    for el in data.get("elements", []):
        tags = el.get("tags") or {}
        name = tags.get("name") or tags.get("name:ru")
        if not name:
            continue
        addr_parts = [
            tags.get("addr:street", ""),
            tags.get("addr:housenumber", ""),
        ]
        address = ", ".join(p for p in addr_parts if p).strip(", ")
        rows.append(
            {
                "name": name,
                "address": address,
                "metro": tags.get("subway", "") or tags.get("nearby_station", ""),
                "capacity": int(tags["capacity"]) if tags.get("capacity", "").isdigit() else None,
                "description": tags.get("description") or tags.get("note") or "",
                "source_url": f"https://www.openstreetmap.org/{el.get('type')}/{el.get('id')}",
                "attribution": "openstreetmap",
                "osm_tags": {k: tags[k] for k in sorted(tags) if k.startswith(("amenity", "tourism", "building", "addr"))},
            }
        )
    json.dump({"count": len(rows), "venues": rows}, sys.stdout, ensure_ascii=False, indent=2)
    sys.stdout.write("\n")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
