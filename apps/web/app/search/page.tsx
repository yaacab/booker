import type { Metadata } from "next";
import Link from "next/link";
import { CatalogFilters } from "@/components/CatalogFilters";
import { CHIP, categoryLabel, PILOT_CITIES } from "@/lib/copy";
import { formatDay, formatWhen, initials, money } from "@/lib/format";

export async function generateMetadata({
  searchParams,
}: {
  searchParams: Promise<{ city?: string }>;
}): Promise<Metadata> {
  const q = await searchParams;
  const city = q.city || "Москва";
  return {
    title: `Каталог — ${city}`,
    alternates: { canonical: "/search" },
  };
}

const API =
  process.env.BOOKER_INTERNAL_API_URL ||
  process.env.NEXT_PUBLIC_API_URL ||
  "http://127.0.0.1:8000";

type SearchItem = {
  id: string;
  name: string;
  city: string;
  category: string;
  verified: boolean;
  has_calendar: boolean;
  open_slots?: number;
  next_open_at?: string | null;
  tariffs?: { honorarium_rub: number }[];
};

function slotState(item: SearchItem): { label: string; cls: string } {
  if ((item.open_slots ?? 0) > 0 && item.verified) return { label: CHIP.slotOk, cls: "ok" };
  if ((item.open_slots ?? 0) > 0 && !item.verified) return { label: CHIP.slotWait, cls: "wait" };
  return { label: CHIP.slotNone, cls: "live" };
}

export default async function SearchPage({
  searchParams,
}: {
  searchParams: Promise<{ city?: string; date?: string; category?: string }>;
}) {
  const q = await searchParams;
  const city = q.city || "Москва";
  const params = new URLSearchParams();
  params.set("city", city);
  if (q.category) params.set("category", q.category);
  if (q.date) params.set("date", `${q.date}T00:00:00+03:00`);
  let items: SearchItem[] = [];
  let venues: SearchItem[] = [];
  let error: string | null = null;
  try {
    const res = await fetch(`${API}/catalog/search?${params.toString()}`, { cache: "no-store" });
    if (res.ok) {
      const data = await res.json();
      items = data.items ?? [];
      venues = data.venues ?? [];
    } else error = "Каталог временно недоступен.";
  } catch {
    error = "Каталог временно недоступен.";
  }
  const empty = items.length === 0 && venues.length === 0 && !error;
  return (
    <main className="page-enter">
      <p className="kicker">Каталог с проверкой календаря</p>
      <h1>Свободные артисты и площадки</h1>
      <div className="catalog-layout">
        <CatalogFilters city={city} date={q.date} category={q.category} />
        <div>
          <p className="timeline">
            {city}
            {q.date ? ` · ${formatDay(`${q.date}T12:00:00+03:00`)}` : " · дата не выбрана — показываем ближайший свободный слот"}
            {q.category ? ` · ${categoryLabel(q.category)}` : ""}
          </p>
          {!(PILOT_CITIES as readonly string[]).includes(city) ? (
            <article className="card empty">
              <h2>Пилотный каталог работает в Москве</h2>
              <p>
                Для города {city} календарная выдача пока не подключена. Можно создать заявку — оператор поможет с подбором.
              </p>
              <p style={{ display: "flex", gap: 8, flexWrap: "wrap", marginTop: 12 }}>
                <Link className="btn" href="/search?city=Москва">
                  Смотреть Москву
                </Link>
                <a className="btn secondary" href="mailto:hello@bukergo.ru?subject=Другой%20город">
                  Связаться с оператором
                </a>
              </p>
            </article>
          ) : null}
          {error ? <p>{error}</p> : null}
          {empty ? (
            <article className="card empty">
              <h2>{q.date ? "На выбранную дату свободных вариантов нет" : "По заданным условиям ничего не найдено"}</h2>
              <p>
                {q.date
                  ? "Попробуйте соседнюю дату, измените формат или отправьте заявку оператору."
                  : "Измените город, формат или другие параметры поиска."}
              </p>
              <p style={{ display: "flex", gap: 8, flexWrap: "wrap", marginTop: 12 }}>
                <Link className="btn" href="/events/new">
                  Создать заявку
                </Link>
                <a className="btn secondary" href="mailto:hello@bukergo.ru?subject=Дата%20занята">
                  Связаться с оператором
                </a>
              </p>
            </article>
          ) : null}
          {items.length > 0 ? (
            <>
              {venues.length > 0 ? <h2>Артисты</h2> : null}
              <div className="grid">
                {items.map((item) => {
                  const st = slotState(item);
                  return (
                    <Link className="card" key={item.id} href={`/artists/${item.id}${q.date ? `?date=${q.date}` : ""}`}>
                      <div className="card-head">
                        <span className="avatar" aria-hidden>
                          {initials(item.name)}
                        </span>
                        <strong>{item.name}</strong>
                      </div>
                      <div>
                        {item.city} · {categoryLabel(item.category)}
                      </div>
                      <p>
                        <span className={`chip ${st.cls}`}>{st.label}</span>{" "}
                        {item.verified ? (
                          <span className="chip ok">{CHIP.verified}</span>
                        ) : (
                          <span className="chip wait">{CHIP.pending}</span>
                        )}
                      </p>
                      <p className="mono">
                        {q.date ? `слот на ${formatDay(`${q.date}T12:00:00+03:00`)}` : formatWhen(item.next_open_at)}
                      </p>
                      {item.tariffs?.[0] ? (
                        <p className="timeline">ориентир от {money(item.tariffs[0].honorarium_rub)}</p>
                      ) : null}
                    </Link>
                  );
                })}
              </div>
            </>
          ) : null}
          {venues.length > 0 ? (
            <>
              {items.length > 0 ? <h2>Площадки</h2> : null}
              <div className="grid">
                {venues.map((item) => {
                  const st = slotState(item);
                  return (
                    <Link className="card" key={item.id} href={`/venues/${item.id}${q.date ? `?date=${q.date}` : ""}`}>
                      <div className="card-head">
                        <span className="avatar" aria-hidden>
                          {initials(item.name)}
                        </span>
                        <strong>{item.name}</strong>
                      </div>
                      <div>
                        {item.city} · площадка
                      </div>
                      <p>
                        <span className={`chip ${st.cls}`}>{st.label}</span>{" "}
                        {item.verified ? (
                          <span className="chip ok">{CHIP.verified}</span>
                        ) : (
                          <span className="chip wait">{CHIP.pending}</span>
                        )}
                      </p>
                      <p className="mono">
                        {q.date ? `слот на ${formatDay(`${q.date}T12:00:00+03:00`)}` : formatWhen(item.next_open_at)}
                      </p>
                      {item.tariffs?.[0] ? (
                        <p className="timeline">ориентир от {money(item.tariffs[0].honorarium_rub)}</p>
                      ) : null}
                    </Link>
                  );
                })}
              </div>
            </>
          ) : null}
        </div>
      </div>
    </main>
  );
}
