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
# Keep this list intentionally narrow. Earlier versions contained unrelated
# identifiers (cemetery, national park, archive and a municipality), which
# polluted the Moscow venue queue.
QUERY = """
SELECT DISTINCT
  ?item ?itemLabel ?itemDescription ?matchedType ?matchedTypeLabel
  ?coord ?website ?streetAddress ?street ?streetLabel ?housenumber ?image
WHERE {
  ?item wdt:P131* wd:Q649;
        wdt:P31/wdt:P279* ?matchedType.
  VALUES ?matchedType {
    wd:Q24354
    wd:Q1329623
    wd:Q41253
    wd:Q57660343
    wd:Q207694
    wd:Q24699794
    wd:Q15243209
  }
  OPTIONAL { ?item wdt:P625 ?coord. }
  OPTIONAL { ?item wdt:P856 ?website. }
  OPTIONAL { ?item wdt:P6375 ?streetAddress. }
  OPTIONAL { ?item wdt:P669 ?street. }
  OPTIONAL { ?item wdt:P670 ?housenumber. }
  OPTIONAL { ?item wdt:P18 ?image. }
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


def _commons_source(image_url: str) -> str:
    if not image_url:
        return ""
    marker = "/Special:FilePath/"
    if marker not in image_url:
        return image_url
    filename = urllib.parse.unquote(image_url.split(marker, 1)[1])
    return "https://commons.wikimedia.org/wiki/File:" + urllib.parse.quote(
        filename.replace(" ", "_"), safe="():,_-."
    )


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
        description = (b.get("itemDescription") or {}).get("value") or ""
        venue_type = (b.get("matchedTypeLabel") or {}).get("value") or ""
        street_address = (b.get("streetAddress") or {}).get("value") or ""
        street = (b.get("streetLabel") or {}).get("value") or ""
        if not street or street.startswith("Q"):
            street = (b.get("street") or {}).get("value") or ""
        if street.startswith("http"):
            street = ""
        house = (b.get("housenumber") or {}).get("value") or ""
        lat, lon = _parse_coord((b.get("coord") or {}).get("value") or "")
        address_parts = [p for p in (street, house) if p]
        address = street_address or ", ".join(address_parts)
        if not address and lat is not None:
            address = f"{lat:.5f},{lon:.5f}"
        if not address:
            continue
        key = f"{name.lower()}|{address}"
        if key in seen:
            continue
        seen.add(key)
        image = (b.get("image") or {}).get("value") or ""
        quality = 25
        if website:
            quality += 40
        if any(c.isalpha() for c in address):
            quality += 20
        if description:
            quality += 10
        if image:
            quality += 10
        sources = [
            {
                "field_name": "name,address,description,venue_type",
                "source_url": item,
                "source_kind": "wikidata_cc0",
            }
        ]
        if website:
            sources.append(
                {
                    "field_name": "official_website",
                    "source_url": item,
                    "source_kind": "wikidata_cc0",
                }
            )
        photos = (
            [
                {
                    "photo_url": image,
                    "photo_source_url": _commons_source(image),
                    "photo_rights_status": "licensed",
                }
            ]
            if image
            else []
        )
        rows.append(
            {
                "name": name.strip(),
                "address": address,
                "district": "",
                "metro": "",
                "capacity": None,
                "description": description,
                "source_url": item,
                "attribution": "wikidata",
                "official_website": website,
                "venue_type": venue_type,
                "sources": sources,
                "photos": photos,
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
