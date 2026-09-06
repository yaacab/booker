"use client";

import Link from "next/link";
import { FavoriteToggle, type FavoriteTargetType } from "@/components/FavoriteToggle";
import { CHIP, categoryLabel } from "@/lib/copy";
import { formatDay, formatWhen, initials, money } from "@/lib/format";

type CatalogItem = {
  id: string;
  name: string;
  city: string;
  category?: string;
  verified: boolean;
  open_slots?: number;
  next_open_at?: string | null;
  tariffs?: { honorarium_rub: number }[];
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

  return (
    <article className="card">
      <div className="card-head">
        <Link href={href} style={{ display: "flex", gap: 12, alignItems: "center", flex: 1, minWidth: 0 }}>
          <span className="avatar" aria-hidden>
            {initials(item.name)}
          </span>
          <strong>{item.name}</strong>
        </Link>
        <FavoriteToggle compact targetType={kind} targetId={item.id} />
      </div>
      <Link href={href} style={{ color: "inherit", textDecoration: "none" }}>
        {kind === "artist" ? (
          <div>
            {item.city} · {categoryLabel(item.category || "")}
          </div>
        ) : (
          <div>
            {item.city} · площадка
            {item.metro ? ` · м. ${item.metro}` : ""}
            {hallHint ? ` · зал до ${hallHint.capacity}` : ""}
          </div>
        )}
        {kind === "venue" && item.address ? <p className="timeline">{item.address}</p> : null}
        <p>
          <span className={`chip ${st.cls}`}>{st.label}</span>{" "}
          {kind === "venue" && item.listing_origin === "open_data" ? (
            <span className="chip wait">{CHIP.openDataVenue}</span>
          ) : kind === "venue" && synthetic ? (
            <span className="chip wait">{CHIP.syntheticCalendar}</span>
          ) : item.verified ? (
            <span className="chip ok">{CHIP.verified}</span>
          ) : (
            <span className="chip wait">{CHIP.pending}</span>
          )}
        </p>
        <p className="mono">
          {date ? `слот на ${formatDay(`${date}T12:00:00+03:00`)}` : formatWhen(item.next_open_at)}
        </p>
        {item.tariffs?.[0] ? (
          <p className="timeline">ориентир от {money(item.tariffs[0].honorarium_rub)}</p>
        ) : kind === "venue" ? (
          <p className="timeline">цена по запросу</p>
        ) : null}
      </Link>
    </article>
  );
}
