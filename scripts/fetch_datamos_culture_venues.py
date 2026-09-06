#!/usr/bin/env python3
"""Fetch Moscow culture institutions from data.mos.ru open API.

Dataset: «Интерактивная карта учреждений культуры города Москвы».
Default dataset id is discovered via /v1/datasets search; override with --dataset-id.

Usage:
  python scripts/fetch_datamos_culture_venues.py --out /tmp/datamos_culture_raw.json
  DATAMOS_API_KEY=... python scripts/fetch_datamos_culture_venues.py --out /tmp/datamos.json

Requires network. API key is optional on some endpoints; set DATAMOS_API_KEY if 403.
"""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.parse
import urllib.request

API_BASE = "https://apidata.mos.ru/v1"
# Open mirror used when DATAMOS_API_KEY is missing (community dump of data.mos tables).
APICRAFTER_URL = "https://api.crftr.net/open/rawapi/v3/datamos/interactivemap"
# Known historical id for culture interactive map; may change — discovery preferred.
DEFAULT_DATASET_HINT = "Интерактивная карта учреждений культуры"
# Fallback dataset ids from public mosopendata catalog (culture venues).
FALLBACK_DATASET_IDS = (526, 493, 531, 528, 530)  # interactive map / DK / theatres / concerts / museums

# Categories that typically have rentable / event halls.
INCLUDE_CATEGORY_RE = re.compile(
    r"дом\s+культур|культурн(ый|ого)\s+центр|концертн|театр|музей|галере|библиоте|"
    r"клуб|филармон|цирк|кинотеатр|выставоч|дворец\s+культур|парк\s+культур|"
    r"arts?\s*centre|concert|theatre|museum|gallery|library|community",
    re.IGNORECASE,
)
EXCLUDE_CATEGORY_RE = re.compile(
    r"кружок|секци[яи]|студия\s+танц|детск(ая|ий)\s+школ|школа\s+искусств|"
    r"музыкальн(ая|ой)\s+школ",
    re.IGNORECASE,
)


def _api_get(path: str, params: dict | None = None) -> object:
    params = dict(params or {})
    key = os.environ.get("DATAMOS_API_KEY", "").strip()
    if key:
        params["api_key"] = key
    qs = urllib.parse.urlencode(params)
    url = f"{API_BASE}{path}"
    if qs:
        url = f"{url}?{qs}"
    req = urllib.request.Request(url, method="GET")
    req.add_header("User-Agent", "booker-venue-curator/1.0 (bukergo.ru; research)")
    req.add_header("Accept", "application/json")
    with urllib.request.urlopen(req, timeout=180) as resp:
        return json.load(resp)


def discover_dataset_id(hint: str = DEFAULT_DATASET_HINT) -> int | None:
    try:
        data = _api_get("/datasets", {"$top": 500, "$inlinecount": "allpages"})
    except urllib.error.HTTPError as exc:
        print(f"dataset list failed: {exc}", file=sys.stderr)
        return None
    items = data if isinstance(data, list) else (data.get("Items") or data.get("items") or [])
    hint_l = hint.lower()
    for item in items:
        caption = str(item.get("Caption") or item.get("caption") or "")
        if hint_l in caption.lower() or "учреждений культуры" in caption.lower():
            return int(item["Id"] if "Id" in item else item["id"])
    return None


def _cell(row: dict) -> dict:
    return row.get("Cells") or row.get("cells") or row


def _location_address(cells: dict) -> str:
    loc = cells.get("Location") or cells.get("ObjectAddress") or ""
    if isinstance(loc, list) and loc:
        first = loc[0]
        if isinstance(first, dict):
            return str(
                first.get("Address")
                or first.get("address")
                or first.get("FullAddress")
                or ""
            ).strip()
        return str(first).strip()
    if isinstance(loc, dict):
        return str(loc.get("Address") or loc.get("address") or "").strip()
    return str(loc).strip()


def _category_ok(category: str) -> bool:
    if not category:
        return True  # keep unknowns; rank later
    if EXCLUDE_CATEGORY_RE.search(category):
        return False
    if INCLUDE_CATEGORY_RE.search(category):
        return True
    # keep broad culture objects without matching exclude
    return "культур" in category.lower() or "театр" in category.lower()


def parse_rows(rows: list) -> list[dict]:
    out: list[dict] = []
    seen: set[str] = set()
    for row in rows:
        cells = _cell(row)
        name = str(cells.get("CommonName") or cells.get("FullName") or "").strip()
        if not name:
            continue
        category = str(cells.get("Category") or "")
        if not _category_ok(category):
            continue
        address = _location_address(cells)
        district = str(cells.get("District") or "")
        if isinstance(cells.get("District"), list):
            district = ", ".join(str(x) for x in cells["District"])
        website = str(cells.get("WebSite") or cells.get("Website") or "").strip()
        if website and not website.startswith("http"):
            website = "https://" + website
        global_id = cells.get("global_id") or row.get("global_id") or row.get("Number")
        source_url = website or (
            f"https://data.mos.ru/opendata/search?q={urllib.parse.quote(name)}"
            if not global_id
            else f"https://data.mos.ru/opendata?id={global_id}"
        )
        dedupe_key = f"{name.lower()}|{address.lower()}"
        if dedupe_key in seen:
            continue
        seen.add(dedupe_key)
        quality = 20
        if website:
            quality += 40
        if address and any(c.isalpha() for c in address):
            quality += 30
        if INCLUDE_CATEGORY_RE.search(category):
            quality += 15
        out.append(
            {
                "name": name,
                "address": address or "Москва",
                "district": district,
                "metro": "",
                "capacity": None,
                "description": f"{category}".strip(" ·") if category else "Учреждение культуры (data.mos.ru)",
                "source_url": source_url,
                "attribution": "data.mos.ru",
                "category": category,
                "quality": quality,
            }
        )
    out.sort(key=lambda r: (-int(r.get("quality") or 0), r["name"].lower()))
    return out


def fetch_rows(dataset_id: int) -> list:
    all_rows: list = []
    skip = 0
    page = 1000
    while True:
        batch = _api_get(f"/datasets/{dataset_id}/rows", {"$top": page, "$skip": skip})
        if not isinstance(batch, list):
            batch = batch.get("Items") or batch.get("items") or []
        if not batch:
            break
        all_rows.extend(batch)
        if len(batch) < page:
            break
        skip += page
        if skip > 20000:
            break
    return all_rows


def fetch_apicrafter() -> list[dict]:
    """Pull interactivemap via open apicrafter mirror (no API key)."""
    all_items: list[dict] = []
    page = 1
    while page <= 40:
        url = f"{APICRAFTER_URL}?max_results=50&page={page}"
        req = urllib.request.Request(url, method="GET")
        req.add_header("User-Agent", "booker-venue-curator/1.0 (bukergo.ru; research)")
        req.add_header("Accept", "application/json")
        with urllib.request.urlopen(req, timeout=120) as resp:
            data = json.load(resp)
        items = data.get("_items") or data.get("items") or []
        if not items:
            break
        # Normalize to data.mos row shape
        for item in items:
            all_items.append({"Cells": item})
        meta = data.get("_meta") or {}
        total = int(meta.get("total") or 0)
        if total and len(all_items) >= total:
            break
        if len(items) < 50:
            break
        page += 1
    return all_items


def fetch(dataset_id: int | None = None) -> dict:
    rows: list = []
    ds_id: int | str | None = dataset_id
    source = "data.mos.ru"

    if os.environ.get("DATAMOS_API_KEY", "").strip():
        ds_id = dataset_id or discover_dataset_id()
        if ds_id is None:
            for candidate in FALLBACK_DATASET_IDS:
                try:
                    rows = fetch_rows(candidate)
                    if rows:
                        ds_id = candidate
                        break
                except Exception as exc:  # noqa: BLE001
                    print(f"dataset {candidate} failed: {exc}", file=sys.stderr)
        else:
            rows = fetch_rows(int(ds_id))
    else:
        print("DATAMOS_API_KEY unset — using apicrafter open mirror", file=sys.stderr)
        try:
            rows = fetch_apicrafter()
            ds_id = "interactivemap"
            source = "data.mos.ru (apicrafter mirror)"
        except Exception as exc:
            print(f"apicrafter failed: {exc}", file=sys.stderr)
            raise RuntimeError(
                "Could not fetch data.mos culture venues. "
                "Set DATAMOS_API_KEY or check network."
            ) from exc

    if not rows:
        raise RuntimeError("data.mos culture fetch returned 0 rows")

    venues = parse_rows(rows)
    return {
        "count": len(venues),
        "source": source,
        "dataset_id": ds_id,
        "venues": venues,
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--out", type=str, default="", help="Write JSON to file")
    parser.add_argument("--dataset-id", type=int, default=0, help="Override dataset id")
    args = parser.parse_args()
    try:
        payload = fetch(args.dataset_id or None)
    except Exception as exc:  # noqa: BLE001 — CLI surface
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
