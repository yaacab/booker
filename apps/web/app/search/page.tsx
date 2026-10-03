import type { Metadata } from "next";
import Link from "next/link";
import { CatalogFilters, type CategoryChip } from "@/components/CatalogFilters";
import { CatalogSearchResults, type SearchItem } from "@/components/CatalogSearchResults";
import { CATEGORY, categoryLabel, PILOT_CITIES } from "@/lib/copy";
import { formatDay } from "@/lib/format";

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

function fallbackCategories(): CategoryChip[] {
  return Object.entries(CATEGORY).map(([code, title]) => ({ code, title }));
}

async function loadCategories(): Promise<CategoryChip[]> {
  try {
    const res = await fetch(`${API}/categories`, { cache: "no-store" });
    if (!res.ok) return fallbackCategories();
    const data = await res.json();
    const items = Array.isArray(data.items) ? data.items : [];
    const mapped = items
      .map((c: { code?: string; title?: string }) => ({
        code: String(c.code || ""),
        title: c.title || categoryLabel(c.code),
      }))
      .filter((c: CategoryChip) => c.code);
    return mapped.length ? mapped : fallbackCategories();
  } catch {
    return fallbackCategories();
  }
}

type SearchQuery = {
  city?: string;
  date?: string;
  category?: string;
  event?: string;
  requirement?: string;
  exclude?: string;
  kind?: string;
  format?: string;
  travel?: string;
  budget_max?: string;
  guests?: string;
  seating?: string;
  cursor?: string;
};

export default async function SearchPage({
  searchParams,
}: {
  searchParams: Promise<SearchQuery>;
}) {
  const q = await searchParams;
  const city = q.city || "Москва";
  const extra = new URLSearchParams();
  if (q.date) extra.set("date", q.date);
  if (q.event) extra.set("event", q.event);
  if (q.requirement) extra.set("requirement", q.requirement);
  if (q.exclude) extra.set("exclude", q.exclude);
  if (q.kind) extra.set("kind", q.kind);
  if (q.format) extra.set("format", q.format);
  if (q.travel) extra.set("travel", q.travel);
  if (q.budget_max) extra.set("budget_max", q.budget_max);
  if (q.guests) extra.set("guests", q.guests);
  if (q.seating) extra.set("seating", q.seating);
  const itemQs = extra.toString();
  const params = new URLSearchParams();
  params.set("city", city);
  if (q.category) params.set("category", q.category);
  if (q.date) params.set("date", `${q.date}T00:00:00+03:00`);
  if (q.exclude) params.set("exclude", q.exclude);
  if (q.kind) params.set("kind", q.kind);
  if (q.format) params.set("format", q.format);
  if (q.travel === "true" || q.travel === "false") params.set("travel", q.travel);
  if (q.budget_max) params.set("budget_max", q.budget_max);
  if (q.guests) params.set("guests", q.guests);
  if (q.seating) params.set("seating", q.seating);
  if (q.cursor) params.set("cursor", q.cursor);
  let items: SearchItem[] = [];
  let venues: SearchItem[] = [];
  let nextCursor: string | null = null;
  let error: string | null = null;
  const [catalogRes, categories] = await Promise.all([
    fetch(`${API}/catalog/search-page?${params.toString()}`, { cache: "no-store" }).catch(() => null),
    loadCategories(),
  ]);
  try {
    if (catalogRes?.ok) {
      const data = await catalogRes.json();
      items = data.items ?? [];
      venues = data.venues ?? [];
      nextCursor = typeof data.next_cursor === "string" ? data.next_cursor : null;
    } else error = "Каталог временно недоступен.";
  } catch {
    error = "Каталог временно недоступен.";
  }
  const empty = items.length === 0 && venues.length === 0 && !nextCursor && !error;
  const filterParams = new URLSearchParams(params);
  filterParams.delete("cursor");
  return (
    <main className="page-enter catalog-page">
      <header className="workspace-heading">
        <div><p className="kicker">Люди и места для вашего события</p>
        <h1>Найдите свою команду</h1></div>
        <Link className="btn secondary" href="/cabinet/customer/favorites">Избранное</Link>
      </header>
      <div className="catalog-layout">
        <CatalogFilters
          city={city}
          date={q.date}
          category={q.category}
          categories={categories}
          event={q.event}
          requirement={q.requirement}
          exclude={q.exclude}
          kind={q.kind}
          format={q.format}
          travel={q.travel}
          budget_max={q.budget_max}
          guests={q.guests}
          seating={q.seating}
        />
        <div>
          <p className="timeline">
            {city}
            {q.date ? ` · ${formatDay(`${q.date}T12:00:00+03:00`)}` : " · дата не выбрана — показываем ближайший свободный слот"}
            {q.category
              ? ` · ${categories.find((c) => c.code === q.category)?.title || categoryLabel(q.category)}`
              : ""}
            {q.guests ? ` · от ${q.guests} гостей` : ""}
            {q.format ? ` · формат «${q.format}»` : ""}
            {q.exclude ? " · без ранее отменённых" : ""}
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
          {!error ? (
            <CatalogSearchResults
              key={params.toString()}
              initialItems={items}
              initialVenues={venues}
              initialCursor={nextCursor}
              filters={filterParams.toString()}
              detailQuery={itemQs}
              date={q.date}
            />
          ) : null}
        </div>
      </div>
    </main>
  );
}
