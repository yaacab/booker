#!/usr/bin/env python3
"""Merge curated wave-1 + OSM + data.mos into data/moscow_venues_open.json (~300).

Usage:
  python scripts/merge_moscow_venues_open.py \\
    --curated /tmp/moscow_venues_wave1.json \\
    --osm /tmp/osm_venues_raw.json \\
    --datamos /tmp/datamos_culture_raw.json \\
    --wikidata /tmp/wikidata_venues_raw.json \\
    --out data/moscow_venues_open.json \\
    --target 300
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path

TARGET_DEFAULT = 300
TARGET_MIN = 290
TARGET_MAX = 320


def _slug_name(name: str) -> str:
    s = name.lower().strip()
    s = s.replace("ё", "е")
    s = re.sub(r"[«»\"'`]", "", s)
    s = re.sub(r"\b(ooo|ao|zao|пао|гбу|гбук|музей|театр|дом культуры|дк)\b", " ", s)
    s = re.sub(r"[^a-z0-9а-я]+", " ", s, flags=re.IGNORECASE)
    return re.sub(r"\s+", " ", s).strip()


def _norm_addr(address: str) -> str:
    s = (address or "").lower().replace("ё", "е")
    s = re.sub(r"\b(ул\.?|улица|пр-?т\.?|проспект|пер\.?|переулок|наб\.?|шоссе|д\.?)\b", " ", s)
    s = re.sub(r"[^a-z0-9а-я]+", " ", s, flags=re.IGNORECASE)
    return re.sub(r"\s+", " ", s).strip()


def _dedupe_key(name: str, address: str) -> str:
    return f"{_slug_name(name)}|{_norm_addr(address)}"


def _is_coord_address(address: str) -> bool:
    return bool(re.fullmatch(r"-?\d+\.\d+\s*,\s*-?\d+\.\d+", (address or "").strip()))


def _quality(row: dict, *, curated: bool = False) -> int:
    if curated:
        return 10_000 + int(row.get("tariff_from_rub") or 0) // 1000
    q = int(row.get("quality") or 0)
    if row.get("attribution") == "data.mos.ru":
        q += 5
    if row.get("capacity"):
        q += 5
    if row.get("description"):
        q += 3
    if _is_coord_address(str(row.get("address") or "")):
        q -= 20
    return q


def _catalog_row(row: dict) -> dict:
    out = {
        "name": str(row["name"]).strip(),
        "address": str(row.get("address") or "").strip(),
        "district": str(row.get("district") or "").strip(),
        "metro": str(row.get("metro") or "").strip(),
        "capacity": int(row["capacity"]) if row.get("capacity") else None,
        "description": str(row.get("description") or "").strip(),
        "source_url": str(row.get("source_url") or "").strip(),
        "attribution": str(row.get("attribution") or "openstreetmap").strip(),
    }
    if row.get("tariff_from_rub") is not None:
        try:
            out["tariff_from_rub"] = int(row["tariff_from_rub"])
        except (TypeError, ValueError):
            pass
    # Drop null capacity for cleaner JSON
    if out["capacity"] is None:
        del out["capacity"]
    return out


def load_venues(path: Path | None) -> list[dict]:
    if not path or not path.is_file():
        return []
    data = json.loads(path.read_text(encoding="utf-8"))
    return list(data.get("venues") or [])


def merge(
    curated: list[dict],
    osm: list[dict],
    datamos: list[dict],
    *,
    target: int,
) -> list[dict]:
    # Prefer curated; then rank OSM+datamos by quality.
    chosen: list[tuple[int, dict]] = []
    keys: set[str] = set()
    source_urls: set[str] = set()

    def try_add(row: dict, *, curated_flag: bool) -> bool:
        name = str(row.get("name") or "").strip()
        address = str(row.get("address") or "").strip()
        if not name or not address:
            return False
        key = _dedupe_key(name, address)
        url = str(row.get("source_url") or "").strip()
        if key in keys:
            return False
        if url and url in source_urls:
            return False
        slug = _slug_name(name)
        addr_n = _norm_addr(address)
        # Same name + same/empty-ish address → duplicate; different street → keep.
        for _, existing in chosen:
            if _slug_name(existing["name"]) != slug:
                continue
            ex_addr = _norm_addr(existing.get("address") or "")
            if not addr_n or not ex_addr or addr_n == ex_addr or addr_n in ex_addr or ex_addr in addr_n:
                return False
        keys.add(key)
        if url:
            source_urls.add(url)
        chosen.append((_quality(row, curated=curated_flag), _catalog_row(row)))
        return True

    for row in curated:
        try_add(row, curated_flag=True)

    bulk = [(_quality(r), r) for r in osm + datamos]
    bulk.sort(key=lambda t: (-t[0], t[1].get("name", "").lower()))
    for _, row in bulk:
        if len(chosen) >= target:
            break
        try_add(row, curated_flag=False)

    chosen.sort(key=lambda t: (-t[0], t[1]["name"].lower()))
    # Keep curated order first: re-sort so curated (quality>=10000) stay at top stable
    return [row for _, row in chosen[: max(target, TARGET_MIN)]]


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--curated", type=Path, required=True)
    parser.add_argument("--osm", type=Path, default=None)
    parser.add_argument("--datamos", type=Path, default=None)
    parser.add_argument("--wikidata", type=Path, default=None)
    parser.add_argument("--out", type=Path, required=True)
    parser.add_argument("--target", type=int, default=TARGET_DEFAULT)
    args = parser.parse_args()

    curated = load_venues(args.curated)
    osm = load_venues(args.osm)
    datamos = load_venues(args.datamos)
    wikidata = load_venues(args.wikidata)
    bulk = osm + datamos + wikidata

    # Preserve wave-1: rows that already have tariff_from_rub OR description length > 40
    # when input curated count <= 50; otherwise use all curated as base.
    if len(curated) <= 50:
        base = curated
    else:
        # Re-merge: prefer previous curated-looking entries (with tariff) as base
        base = [r for r in curated if r.get("tariff_from_rub") is not None]
        if len(base) < 20:
            base = curated[:26]

    merged = merge(base, bulk, [], target=args.target)
    n = len(merged)
    if n < TARGET_MIN:
        print(
            f"warning: only {n} venues after merge (want {TARGET_MIN}-{TARGET_MAX}). "
            "Fetch larger OSM/datamos dumps.",
            file=sys.stderr,
        )
    if n > TARGET_MAX:
        merged = merged[:TARGET_MAX]
        n = len(merged)

    payload = {
        "version": 2,
        "city": "Москва",
        "license_note": (
            "Открытый каталог: кураторская волна 1 + OSM (ODbL) + Wikidata (CC0) + data.mos.ru. "
            "Календарь синтетический; не живой скрейп коммерческих агрегаторов."
        ),
        "venues": merged,
    }
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {n} venues -> {args.out}", file=sys.stderr)
    return 0 if n >= TARGET_MIN else 2


if __name__ == "__main__":
    raise SystemExit(main())
