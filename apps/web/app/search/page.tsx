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
    title: `Кто ещё не занят — ${city}`,
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
      <p className="kicker">Только те, у кого дата в календаре. Остальные просто красивые.</p>
      <h1>Кто ещё не занят</h1>
      <div className="catalog-layout">
        <CatalogFilters city={city} date={q.date} category={q.category} />
        <div>
          <p className="timeline">
            {city}
            {q.date ? ` · ${formatDay(`${q.date}T12:00:00+03:00`)}` : " · дату не выбрали — покажем ближайшую дырку"}
            {q.category ? ` · ${categoryLabel(q.category)}` : ""}
          </p>
          {!(PILOT_CITIES as readonly string[]).includes(city) ? (
            <article className="card empty">
              <h2>Пилот крутится в Москве</h2>
              <p>
                В {city} календаря в выдаче ещё нет. Можно собрать вечер и позвать человека — чудес без обещаний.
              </p>
              <p style={{ display: "flex", gap: 8, flexWrap: "wrap", marginTop: 12 }}>
                <Link className="btn" href="/search?city=Москва">
                  Смотреть Москву
                </Link>
                <a className="btn secondary" href="mailto:hello@bukergo.ru?subject=Другой%20город">
                  Позвать человека
                </a>
              </p>
            </article>
          ) : null}
          {error ? <p>{error}</p> : null}
          {empty ? (
            <article className="card empty">
              <h2>{q.date ? "Эта дата уже жената" : "В этой охоте никого"}</h2>
              <p>
                {q.date
                  ? "Другой день, другой жанр — или зовите человека. Чудеса без обещаний он ещё умеет."
                  : "Другой город, другой жанр — или зовите человека. Без календаря сюда не пускаем."}
              </p>
              <p style={{ display: "flex", gap: 8, flexWrap: "wrap", marginTop: 12 }}>
                <Link className="btn" href="/events/new">
                  Собрать вечер
                </Link>
                <a className="btn secondary" href="mailto:hello@bukergo.ru?subject=Дата%20занята">
                  Позвать человека
                </a>
              </p>
            </article>
          ) : null}
          {items.length > 0 ? (
            <>
              {venues.length > 0 ? <h2>На сцене</h2> : null}
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
                        <p className="timeline">от {money(item.tariffs[0].honorarium_rub)} — это ещё не счёт</p>
                      ) : null}
                    </Link>
                  );
                })}
              </div>
            </>
          ) : null}
          {venues.length > 0 ? (
            <>
              {items.length > 0 ? <h2>Крыша</h2> : null}
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
                        <p className="timeline">от {money(item.tariffs[0].honorarium_rub)} — это ещё не счёт</p>
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
