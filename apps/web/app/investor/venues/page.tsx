import type { Metadata } from "next";
import Link from "next/link";
import fs from "node:fs/promises";
import path from "node:path";
import { InvestorVenueCatalog, type InvestorVenue } from "@/components/InvestorVenueCatalog";

export const dynamic = "force-dynamic";

export const metadata: Metadata = {
  title: "300 площадок для выступлений — демо Букера",
  description: "Исследовательская витрина реальных площадок Москвы для инвесторского показа.",
  robots: { index: false, follow: false },
};

const API =
  process.env.BOOKER_INTERNAL_API_URL ||
  process.env.NEXT_PUBLIC_API_URL ||
  "http://127.0.0.1:8000";

async function loadFileFallback(): Promise<InvestorVenue[]> {
  try {
    const filePath = path.resolve(process.cwd(), "../../data/moscow_performance_venues_research.json");
    const payload = JSON.parse(await fs.readFile(filePath, "utf8"));
    return (payload.venues || []).slice(0, 300).map((venue: any) => {
      const photos = (venue.photos || []).map((photo: any) => ({
        url: photo.photo_url,
        source_url: photo.photo_source_url,
        rights_status: photo.photo_rights_status,
      }));
      return {
        id: venue.source_id,
        name: venue.name,
        city: venue.city,
        address: venue.address,
        metro: venue.metro,
        description: venue.description,
        capacity: venue.capacity,
        area_sqm: venue.area_sqm,
        venue_type: venue.venue_type,
        performance_evidence: venue.performance_evidence || [],
        has_stage: venue.has_stage === true,
        has_sound: venue.has_sound === true,
        has_light: venue.has_light === true,
        tariff_from_rub: venue.tariff_from_rub,
        tariff_unit: venue.tariff_unit,
        source_url: venue.source_url,
        source_attribution: venue.attribution,
        cover_photo: photos[0],
        photos,
        photo_notice: "Внешние фото из карточки источника; права для публичной публикации не заявлены.",
        availability_note: "Свободные даты и итоговую смету подтверждает площадка.",
      } satisfies InvestorVenue;
    });
  } catch {
    return [];
  }
}

async function loadVenues(): Promise<{ items: InvestorVenue[]; error?: string }> {
  try {
    const url = API + "/catalog/demo/venues?city=" + encodeURIComponent("Москва") + "&limit=300";
    const response = await fetch(url, { cache: "no-store" });
    if (response.ok) {
      const data = await response.json();
      const items = Array.isArray(data.items) ? data.items : [];
      if (items.length) return { items };
    }
  } catch {
    // Local investor preview can use the checked-in research snapshot.
  }
  const items = await loadFileFallback();
  return items.length ? { items } : { items: [], error: "Демо-каталог пока не загружен." };
}

export default async function InvestorVenuesPage() {
  const { items, error } = await loadVenues();
  return (
    <main className="page-enter investor-venues-page">
      <header className="workspace-heading investor-venues-heading">
        <div>
          <p className="kicker">Исследовательская витрина · Москва</p>
          <h1>300 площадок, где могут выступать артисты</h1>
          <p>
            Реальные карточки с адресами, вместимостью, описаниями, ценой аренды и фотографиями.
            Финальную доступность и смету подтверждает представитель площадки.
          </p>
        </div>
        <Link className="btn secondary" href="/search?city=Москва&kind=venue">Публичный каталог</Link>
      </header>
      <aside className="investor-venue-notice">
        Это отдельное инвесторское демо, а не публичная выдача подтверждённых партнёров. Данные и фото сопровождаются ссылкой на источник; права на внешние изображения Букер не заявляет.
      </aside>
      {error ? <article className="card empty"><h2>{error}</h2><p>Сначала запустите импорт московских площадок.</p></article> : null}
      {!error && items.length === 0 ? <article className="card empty"><h2>Карточки ещё не импортированы</h2></article> : null}
      {items.length ? <InvestorVenueCatalog items={items} /> : null}
    </main>
  );
}
