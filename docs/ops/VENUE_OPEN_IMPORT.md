# Импорт открытых площадок Москвы

Источник правды для seed: [`data/moscow_venues_open.json`](../../data/moscow_venues_open.json) (~300 карточек).

## Что делает импорт

1. Shared org **«Букер · открытый каталог Москва»** (`open-catalog@booker.local`).
2. Для каждой записи JSON: `Venue` + зал «Основной зал» + тариф «Аренда (ориентир)» (если указан `tariff_from_rub`).
3. Синтетические open-слоты:
   - **30 дней** — кураторская волна 1 (есть `tariff_from_rub`);
   - **14 дней** — bulk open-data (OSM / Wikidata / data.mos), чтобы не раздувать БД.
   - Окно 18:00–22:00 MSK, `external_uid=synthetic:open:YYYY-MM-DD`.
4. `listing_origin=open_data`, `availability_mode=synthetic`, `verified=false`.

Площадки сразу видны в `/catalog/search` и Event Studio с бейджем **«календарь ориентировочный»**.

## Команды

```bash
make seed-venues-moscow   # только open-data импорт
make seed                 # demo seed + open-data импорт
```

Идемпотентно: повторный запуск обновляет поля и добирает недостающие слоты.

## Обновление дампа (~300)

Квартальный цикл:

```bash
# 1) Сырые источники (нужен сеть; Overpass/data.mos могут троттлить)
python scripts/fetch_osm_venues_moscow.py --out /tmp/osm_venues_raw.json
python scripts/fetch_wikidata_venues_moscow.py --out /tmp/wikidata_venues_raw.json
# опционально при наличии ключа:
# DATAMOS_API_KEY=... python scripts/fetch_datamos_culture_venues.py --out /tmp/datamos_culture_raw.json

# 2) Слияние с кураторской волной 1 (сохраните её отдельно перед первым merge)
python scripts/merge_moscow_venues_open.py \
  --curated /tmp/moscow_venues_wave1.json \
  --osm /tmp/osm_venues_raw.json \
  --wikidata /tmp/wikidata_venues_raw.json \
  --datamos /tmp/datamos_culture_raw.json \
  --out data/moscow_venues_open.json \
  --target 300

# 3) Импорт
make seed-venues-moscow
```

Сырые дампы **не** сидить в прод напрямую — только через merge (дедуп name+address, приоритет волны 1).

## Перевод на календарь владельца

После контакта с площадкой:

1. Создайте отдельный workspace `kind=venue` для владельца (или передайте Venue в его org).
2. Установите `availability_mode=owner`, `listing_origin=owner`.
3. Удалите/закройте synthetic-слоты (`external_uid LIKE 'synthetic:%'`).
4. Импортируйте iCal или откройте реальные слоты.
5. Пройдите верификацию в админке.

## Лицензии

- **OpenStreetMap** — ODbL; `source_attribution=openstreetmap`.
- **Wikidata** — CC0; `source_attribution=wikidata`.
- **data.mos.ru** — условия портала открытых данных Москвы; `source_attribution=data.mos.ru`.
- Не копировать закрытые каталоги агрегаторов с запретом в ToS.
- Цены в JSON — **публичные ориентиры**, не quote; итог только в OfferVersion.
