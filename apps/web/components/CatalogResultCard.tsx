"use client";

import Link from "next/link";
import { ProfileMedia } from "@/components/ProfileMedia";
import { FavoriteToggle, type FavoriteTargetType } from "@/components/FavoriteToggle";
import { CHIP, categoryLabel } from "@/lib/copy";
import { formatDay, formatWhen, money, guestsLabel } from "@/lib/format";

type CatalogItem = {
  id: string;
  name: string;
  city: string;
  category?: string;
  verified: boolean;
  media_url?: string | null;
  open_slots?: number;
  next_open_at?: string | null;
  tariffs?: { honorarium_rub: number }[];
  capacity?: number;
  address?: string;
  metro?: string;
  availability_mode?: string;
  listing_origin?: string;
  matching_halls?: { id: string; name: string; capacity: number }[];
};

type CatalogResultCardProps = {
  item: CatalogItem;
  kind: FavoriteTargetType;
  href: string;
  date?: string;
};

function slotState(item: CatalogItem): { label: string; cls: string } {
  if (item.availability_mode === "synthetic") {
    return { label: CHIP.syntheticCalendar, cls: "wait" };
  }
  if ((item.open_slots ?? 0) > 0 && item.verified) return { label: CHIP.slotOk, cls: "ok" };
  if ((item.open_slots ?? 0) > 0 && !item.verified) return { label: CHIP.slotWait, cls: "wait" };
  return { label: CHIP.slotNone, cls: "live" };
}

export function CatalogResultCard({ item, kind, href, date }: CatalogResultCardProps) {
  const st = slotState(item);
  const synthetic = item.availability_mode === "synthetic";
  const hallHint = item.matching_halls?.[0];

  const displayedTariff = item.tariffs?.[0];
  const category = kind === "venue" ? "Площадка" : categoryLabel(item.category || "");
  const availabilityTitle = date
    ? `На ${formatDay(`${date}T12:00:00+03:00`)}`
    : item.next_open_at ? `Ближайшая дата: ${formatWhen(item.next_open_at)}` : st.label;

  return (
    <article className={`card catalog-result catalog-result--${kind}`}>
      <div className="catalog-card-media">
        <Link className="catalog-image-link" href={href} aria-label={`Открыть профиль: ${item.name}`}>
          <ProfileMedia src={item.media_url} name={item.name} compact />
        </Link>
        <span className={`catalog-availability chip ${st.cls}`} title={availabilityTitle}>
          <svg aria-hidden="true" viewBox="0 0 20 20"><rect x="3" y="4" width="14" height="13" rx="2" /><path d="M6 2v4M14 2v4M3 8h14M6 11h2M11 11h2" /></svg>
          {st.label}
        </span>
        <FavoriteToggle compact className="catalog-card-favorite" targetType={kind} targetId={item.id} />
      </div>
      <div className="catalog-card-content">
        <div className="card-head">
          <Link href={href}><strong>{item.name}</strong></Link>
          {item.verified ? <span className="catalog-verified-mark" role="img" aria-label={CHIP.verified} title={CHIP.verified}>✓</span> : null}
        </div>
        <p className="catalog-card-location">{category} <span aria-hidden="true">·</span> {item.city}{item.metro ? ` · м. ${item.metro}` : ""}</p>
        <div className="catalog-card-facts">
          {kind === "venue" && (hallHint?.capacity || item.capacity) ? <span>{`До ${guestsLabel(hallHint?.capacity || item.capacity || 0)}`}</span> : null}
          {kind === "venue" && item.listing_origin === "open_data" ? <span className="catalog-origin-note">Владелец не подключён</span> : !item.verified ? <span>Профиль не подтверждён</span> : <span>Профиль подтверждён</span>}
          {hallHint?.name ? <span>{hallHint.name}</span> : null}
        </div>
        {kind === "venue" && item.address ? <p className="catalog-card-address">{item.address}</p> : null}
        {item.next_open_at && !synthetic ? <p className="catalog-card-date">{date ? `На ${formatDay(`${date}T12:00:00+03:00`)}` : `Ближайшая: ${formatWhen(item.next_open_at)}`}</p> : null}
        <div className="catalog-card-footer">
          <p className="catalog-price">{displayedTariff ? <><span>Ориентир</span>{money(displayedTariff.honorarium_rub)}</> : <span className="catalog-price-request">Цена по запросу</span>}</p>
          <Link className="btn secondary catalog-open" href={href}>Выбрать дату <span aria-hidden="true">↗</span></Link>
        </div>
      </div>
    </article>
  );
}
