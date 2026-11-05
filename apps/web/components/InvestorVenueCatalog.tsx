"use client";

import { useMemo, useState } from "react";

export type InvestorVenue = {
  id: string;
  name: string;
  city: string;
  address: string;
  metro: string;
  description: string;
  capacity: number;
  area_sqm?: number | null;
  venue_type: string;
  performance_evidence: string[];
  has_stage: boolean;
  has_sound: boolean;
  has_light: boolean;
  tariff_from_rub: number;
  tariff_unit: string;
  source_url: string;
  source_attribution: string;
  cover_photo: { url: string; source_url?: string; rights_status?: string };
  photos: { url: string; source_url?: string; rights_status?: string }[];
  photo_notice: string;
  availability_note: string;
};

const money = new Intl.NumberFormat("ru-RU", {
  style: "currency",
  currency: "RUB",
  maximumFractionDigits: 0,
});

const evidenceLabels: Record<string, string> = {
  concert_hall_category: "концертный зал",
  dance_hall_category: "танцевальный зал",
  stage: "сцена",
  concert: "концерты",
  sound: "звук",
  microphone: "микрофоны",
  dj: "DJ",
  karaoke: "караоке",
  dancefloor: "танцпол",
  show_light: "свет",
};

export function InvestorVenueCatalog({ items }: { items: InvestorVenue[] }) {
  const [query, setQuery] = useState("");
  const [minGuests, setMinGuests] = useState("");
  const [maxPrice, setMaxPrice] = useState("");
  const [soundOnly, setSoundOnly] = useState(false);

  const visible = useMemo(() => {
    const needle = query.trim().toLocaleLowerCase("ru");
    const guests = Number(minGuests) || 0;
    const budget = Number(maxPrice) || Number.POSITIVE_INFINITY;
    return items.filter((venue) => {
      const haystack = [venue.name, venue.address, venue.metro, venue.description]
        .join(" ")
        .toLocaleLowerCase("ru");
      return (
        (!needle || haystack.includes(needle)) &&
        venue.capacity >= guests &&
        venue.tariff_from_rub <= budget &&
        (!soundOnly || venue.has_sound)
      );
    });
  }, [items, maxPrice, minGuests, query, soundOnly]);

  return (
    <>
      <section className="investor-venue-filters" aria-label="Фильтры площадок">
        <label>
          <span>Название, метро или адрес</span>
          <input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Например, Бауманская" />
        </label>
        <label>
          <span>Гостей от</span>
          <input inputMode="numeric" value={minGuests} onChange={(event) => setMinGuests(event.target.value)} placeholder="50" />
        </label>
        <label>
          <span>Цена до, ₽/час</span>
          <input inputMode="numeric" value={maxPrice} onChange={(event) => setMaxPrice(event.target.value)} placeholder="10 000" />
        </label>
        <label className="investor-venue-check">
          <input type="checkbox" checked={soundOnly} onChange={(event) => setSoundOnly(event.target.checked)} />
          <span>Есть звуковое оснащение</span>
        </label>
      </section>

      <p className="timeline">Показано {visible.length} из {items.length}</p>
      <section className="investor-venue-grid" aria-live="polite">
        {visible.map((venue) => (
          <article className="card investor-venue-card" key={venue.id}>
            <img
              className="investor-venue-cover"
              src={venue.cover_photo.url}
              alt={`Фото площадки «${venue.name}»`}
              loading="lazy"
              decoding="async"
              referrerPolicy="no-referrer"
            />
            <div className="investor-venue-body">
              <div className="investor-venue-title-row">
                <h2>{venue.name}</h2>
                <strong>{money.format(venue.tariff_from_rub)}<small>/час</small></strong>
              </div>
              <p className="timeline">
                {venue.metro ? `м. ${venue.metro} · ` : ""}{venue.capacity} гостей
                {venue.area_sqm ? ` · ${venue.area_sqm} м²` : ""}
              </p>
              <p>{venue.address}</p>
              <div className="investor-venue-signals">
                {venue.performance_evidence.slice(0, 5).map((signal) => (
                  <span className="chip ok" key={signal}>{evidenceLabels[signal] || signal}</span>
                ))}
              </div>
              <details>
                <summary>Описание и фотографии</summary>
                <p>{venue.description}</p>
                <div className="investor-venue-gallery">
                  {venue.photos.slice(0, 5).map((photo, index) => (
                    <img
                      key={photo.url}
                      src={photo.url}
                      alt={`«${venue.name}», фото ${index + 1}`}
                      loading="lazy"
                      decoding="async"
                      referrerPolicy="no-referrer"
                    />
                  ))}
                </div>
                <p className="timeline">{venue.availability_note}</p>
                <p className="timeline">{venue.photo_notice}</p>
                <a href={venue.source_url} target="_blank" rel="noreferrer">Проверить исходную карточку ↗</a>
              </details>
            </div>
          </article>
        ))}
      </section>
    </>
  );
}
