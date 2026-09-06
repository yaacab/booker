#!/usr/bin/env python3
"""Fetch Moscow culture/event venues from Wikidata (fallback when Overpass is slow).

Usage:
  python scripts/fetch_wikidata_venues_moscow.py --out /tmp/wikidata_venues_raw.json
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.parse
import urllib.request

ENDPOINT = "https://query.wikidata.org/sparql"
# Theatre, museum, concert hall, cultural centre, cinema, stadium, exhibition hall, nightclub
QUERY = """
SELECT DISTINCT ?item ?itemLabel ?coord ?website ?street ?housenumber WHERE {
  ?item wdt:P131* wd:Q649;
        wdt:P31/wdt:P279* ?type.
  VALUES ?type {
    wd:Q24354 wd:Q207694 wd:Q20010800 wd:Q1329623 wd:Q41253
    wd:Q483110 wd:Q57660343 wd:Q622425 wd:Q1007870 wd:Q856584
    wd:Q166118 wd:Q24699794 wd:Q46169 wd:Q13926 wd:Q33506
    wd:Q15243209 wd:Q570116 wd:Q210272 wd:Q39614
  }
  OPTIONAL { ?item wdt:P625 ?coord. }
  OPTIONAL { ?item wdt:P856 ?website. }
  OPTIONAL { ?item wdt:P669 ?street. }
  OPTIONAL { ?item wdt:P670 ?housenumber. }
  SERVICE wikibase:label { bd:serviceParam wikibase:language "ru,en". }
}
LIMIT 800
"""


def _parse_coord(value: str) -> tuple[float | None, float | None]:
    # Point(37.6 55.75)
    if not value.startswith("Point("):
        return None, None
    inner = value[6:].rstrip(")")
    parts = inner.split()
    if len(parts) != 2:
        return None, None
    try:
        lon, lat = float(parts[0]), float(parts[1])
        return lat, lon
    except ValueError:
        return None, None


def fetch() -> dict:
    url = ENDPOINT + "?" + urllib.parse.urlencode({"query": QUERY, "format": "json"})
    req = urllib.request.Request(url, method="GET")
    req.add_header("User-Agent", "booker-venue-curator/1.0 (bukergo.ru; research)")
    req.add_header("Accept", "application/sparql-results+json")
    with urllib.request.urlopen(req, timeout=120) as resp:
        data = json.load(resp)
    rows = []
    seen: set[str] = set()
    for b in data.get("results", {}).get("bindings", []):
        name = (b.get("itemLabel") or {}).get("value") or ""
        if not name or name.startswith("Q"):
            continue
        item = (b.get("item") or {}).get("value") or ""
        website = (b.get("website") or {}).get("value") or ""
        street = (b.get("street") or {}).get("value") or ""
        # street may be a Wikidata entity URL — skip entity URLs as address
        if street.startswith("http"):
            street = ""
        house = (b.get("housenumber") or {}).get("value") or ""
        lat, lon = _parse_coord((b.get("coord") or {}).get("value") or "")
        address_parts = [p for p in (street, house) if p]
        address = ", ".join(address_parts)
        if not address and lat is not None:
            address = f"{lat:.5f},{lon:.5f}"
        if not address:
            continue
        key = f"{name.lower()}|{address}"
        if key in seen:
            continue
        seen.add(key)
        quality = 25
        if website:
            quality += 40
        if any(c.isalpha() for c in address):
            quality += 20
        rows.append(
            {
                "name": name.strip(),
                "address": address,
                "district": "",
                "metro": "",
                "capacity": None,
                "description": "Площадка из Wikidata (Москва)",
                "source_url": website or item,
                "attribution": "wikidata",
                "quality": quality,
                "lat": lat,
                "lon": lon,
            }
        )
    rows.sort(key=lambda r: (-int(r.get("quality") or 0), r["name"].lower()))
    return {"count": len(rows), "source": "wikidata", "venues": rows}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=str, default="")
    args = parser.parse_args()
    try:
        payload = fetch()
    except Exception as exc:  # noqa: BLE001
        print(f"error: {exc}", file=sys.stderr)
        return 1
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
