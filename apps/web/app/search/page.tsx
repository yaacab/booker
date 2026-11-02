import type { Metadata } from "next";
import Link from "next/link";
import { MoscowMap } from "@/components/MoscowMap";
import { CatalogFilters, type CategoryChip } from "@/components/CatalogFilters";
import { CatalogResultCard } from "@/components/CatalogResultCard";
import { ServiceResultCard, type PublicServiceItem } from "@/components/ServiceResultCard";
import { CATEGORY, categoryLabel, PILOT_CITIES } from "@/lib/copy";
import { formatDay, pluralRu } from "@/lib/format";

export async function generateMetadata({
  searchParams,
}: {
  searchParams: Promise<{ city?: string;kind?:string }>;
}): Promise<Metadata> {
  const q = await searchParams;
  const city = (q.city || "").trim();
  const titleKind = q.kind === "service" ? "Услуги" : "Каталог";
  return {
    title: city ? `${titleKind} — ${city}` : titleKind,
    alternates: { canonical: "/search" },
    ...(q.kind==="venue"?{robots:{index:false,follow:false}}:{}),
  };
}

const API =
  (process.env.BOOKER_DEMO_GATEWAY === "1" ? "http://127.0.0.1:8031" : undefined) ||
  process.env.BOOKER_INTERNAL_API_URL ||
  process.env.NEXT_PUBLIC_API_URL ||
  "http://127.0.0.1:8000";

type SearchItem = {
  id: string;
  name: string;
  city: string;
  category: string;
  verified: boolean;
  media_url?: string | null;
  capacity?: number;
  has_calendar?: boolean;
  open_slots?: number;
  next_open_at?: string | null;
  tariffs?: { honorarium_rub: number }[];
  address?: string;
  metro?: string;
  district?: string;
  availability_mode?: string;
  listing_origin?: string;
  source_type?: string;
  partnership_status?: string;
  public_disclosure?: string | null;
  matching_halls?: { id: string; name: string; capacity: number }[];
};

function fallbackCategories(): CategoryChip[] {
  return Object.entries(CATEGORY).map(([code, title]) => ({ code, title }));
}

async function loadCategories(): Promise<CategoryChip[]> {
  try {
    const res = await fetch(`${API}/categories`, { cache: "no-store", signal: AbortSignal.timeout(8000) });
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
  district?: string;
  metro?: string;
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
};

export default async function SearchPage({
  searchParams,
}: {
  searchParams: Promise<SearchQuery>;
}) {
  const raw = await searchParams;
  // Venue selection is hidden until venues connect themselves: the research set (third-party photos, prices and texts)
  // is investor-demo only and must not be public.
  if(raw.kind==="venue"){
    return <main className="venue-discovery venue-discovery--soon"><header><p className="eyebrow">Площадки</p><h1>Площадки подключаются</h1>
      <p>Скоро здесь появятся площадки, которые сами разместились в Букере, с фото и условиями от владельцев. Пока опишите событие — оператор подберёт место под ваш формат и бюджет.</p></header>
      <p style={{ display: "flex", gap: 8, flexWrap: "wrap", marginTop: 16 }}><Link className="btn" href="/events/new">Создать заявку</Link><Link className="btn secondary" href="/search?kind=artist">Найти артиста</Link></p></main>;
  }
  const q = { ...raw, kind:raw.kind||"artist", category: raw.kind === "venue" || ((raw.kind === "artist" || raw.kind === "service") && raw.category === "venue") ? undefined : raw.category };
  const city = (q.city || "").trim(); // empty = all cities
  const serviceMode = q.kind === "service";
  const extra = new URLSearchParams();
  if (city) extra.set("city", city);
  if (q.category) extra.set("category", q.category);
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
  if(q.district) extra.set("district",q.district);
  if(q.metro) extra.set("metro",q.metro);
  const itemQs = extra.toString();
  const params = new URLSearchParams();
  if (city) params.set("city", city);
  if (q.category) params.set("category", q.category);
  if (q.date) params.set("date", `${q.date}T00:00:00+03:00`);
  if (q.exclude) params.set("exclude", q.exclude);
  if (q.kind) params.set("kind", q.kind);
  if (q.format) params.set("format", q.format);
  if (q.travel === "true" || q.travel === "false") params.set("travel", q.travel);
  if (q.budget_max) params.set("budget_max", q.budget_max);
  if (q.guests) params.set("guests", q.guests);
  if (q.seating) params.set("seating", q.seating);
  if(q.district) params.set("district",q.district);
  if(q.metro) params.set("metro",q.metro);
  let items: SearchItem[] = [];
  let venues: SearchItem[] = [];
  let services: PublicServiceItem[] = [];
  let error: string | null = null;
  const serviceParams = new URLSearchParams();
  if (q.category) serviceParams.set("category", q.category);
  if (city) serviceParams.set("city", city);
  if (q.budget_max) serviceParams.set("budget_max", q.budget_max);
  const [catalogRes, servicesRes, categories] = await Promise.all([
    serviceMode
      ? Promise.resolve(null)
      : fetch(`${API}/catalog/search?${params.toString()}`, { cache: "no-store", signal: AbortSignal.timeout(8000) }).catch(() => null),
    serviceMode
      ? fetch(`${API}/services/public?${serviceParams.toString()}`, { cache: "no-store", signal: AbortSignal.timeout(8000) }).catch(() => null)
      : Promise.resolve(null),
    loadCategories(),
  ]);
  try {
    if (serviceMode) {
      if (servicesRes?.ok) {
        const data = await servicesRes.json();
        services = Array.isArray(data.items) ? data.items : [];
      } else error = "Каталог услуг временно недоступен.";
    } else if (catalogRes?.ok) {
      const data = await catalogRes.json();
      items = Array.isArray(data.items) ? data.items : [];
      venues = Array.isArray(data.venues) ? data.venues : [];
    } else error = "Каталог временно недоступен.";
  } catch {
    error = serviceMode ? "Каталог услуг временно недоступен." : "Каталог временно недоступен.";
  }
  const empty = serviceMode
    ? services.length === 0 && !error
    : items.length === 0 && venues.length === 0 && !error;
  const total = serviceMode ? services.length : items.length + venues.length;
  return (
    <main className="page-enter catalog-page catalog-reference">
      <header className="catalog-heading">
        <h1>{serviceMode ? <>Услуги для<br />вашего события</> : <>Найдите тех,<br /> кто нужен именно вам</>}</h1>
        <p className="catalog-heading-note">Больше<br />событий<br />для людей<span aria-hidden="true" /></p>
      </header>
      <form key={JSON.stringify(q)} className="catalog-searchbar" action="/search" method="get" aria-label="Быстрый поиск">
        <fieldset className="catalog-kind-switch">
          <legend className="catalog-sr-only">Кого ищем</legend>
          {[{ value: "artist", label: "Артисты" }, { value: "service", label: "Услуги" }].map((choice) => (
            <label key={choice.value}><input type="radio" name="kind" value={choice.value} defaultChecked={(q.kind || "") === choice.value} /><span>{choice.label}</span></label>
          ))}
        </fieldset>
        <label className="catalog-search-field">
          <svg aria-hidden="true" viewBox="0 0 24 24"><rect x="4" y="5" width="16" height="16" rx="3" /><path d="M8 3v4M16 3v4M4 11h16M8 15h2M14 15h2" /></svg>
          <span>Дата<input type="date" name="date" defaultValue={q.date || ""} /></span>
        </label>
        <label className="catalog-search-field">
          <svg aria-hidden="true" viewBox="0 0 24 24"><path d="M20 10c0 6-8 12-8 12S4 16 4 10a8 8 0 1 1 16 0Z" /><circle cx="12" cy="10" r="2.5" /></svg>
          <span>Город<input name="city" defaultValue={city} placeholder="Все города" autoComplete="address-level2" /></span>
        </label>
        <label className="catalog-search-field">
          <svg aria-hidden="true" viewBox="0 0 24 24"><path d="M7 4h6a5 5 0 0 1 0 10H7M9 3v18M6 18h9" /></svg>
          <span>Бюджет, ₽<input aria-label="Бюджет в быстром поиске" type="number" name="budget_max" min="0" defaultValue={q.budget_max || ""} placeholder="Любой" /></span>
        </label>
        {Object.entries(q).filter(([key,value]) => value && !["kind","date","city","budget_max"].includes(key)).map(([key,value]) => <input key={key} type="hidden" name={key} value={value} />)}
        <button className="catalog-find" type="submit"><svg aria-hidden="true" viewBox="0 0 24 24"><circle cx="10.5" cy="10.5" r="6.5" /><path d="m16 16 5 5" /></svg>Найти</button>
      </form>
      <div className="catalog-layout">
        <CatalogFilters
          key={JSON.stringify(q)}
          district={q.district}
          metro={q.metro}
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
        <div className="catalog-results">
          <div className="catalog-results-heading">
            {!error && <p className="catalog-count" role="status">{total} {pluralRu(total, "вариант", "варианта", "вариантов")} для вашего события</p>}
            <Link href="/cabinet/customer/favorites" className="catalog-favorites-link"><span aria-hidden="true">♡</span> Избранное</Link>
          </div>
          <p className="timeline catalog-query-summary">
            {city || "Все города"}
            {q.date ? ` · ${formatDay(`${q.date}T12:00:00+03:00`)}` : " · любые даты"}
            {q.category
              ? ` · ${categories.find((c) => c.code === q.category)?.title || categoryLabel(q.category)}`
              : ""}
            {q.guests ? ` · от ${q.guests} гостей` : ""}
            {q.format ? ` · формат «${q.format}»` : ""}
            {q.exclude ? " · без ранее отменённых" : ""}
          </p>
          {city && !(PILOT_CITIES as readonly string[]).includes(city) ? (
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
          {error ? <article className="card empty" role="alert"><h2>Не получилось загрузить каталог</h2><p>{error} Попробуйте открыть страницу ещё раз.</p><Link className="btn secondary" href={`/search?${new URLSearchParams(Object.entries(q).filter((entry): entry is [string, string] => Boolean(entry[1]))).toString()}`}>Попробовать ещё раз</Link></article> : null}
          {empty ? (
            <article className="card empty">
              <h2>
                {serviceMode
                  ? "В публичном каталоге пока нет опубликованных услуг"
                  : q.date
                    ? "На выбранную дату свободных вариантов нет"
                    : "В публичном каталоге пока нет доступных артистов"}
              </h2>
              <p>
                {serviceMode
                  ? "Показываем только опубликованные услуги привязанных и допущенных к публикации профилей. Можно перейти к артистам или создать заявку."
                  : q.date
                    ? "Попробуйте соседнюю дату или отправьте заявку оператору. Если каталог пуст целиком — смена даты не поможет."
                    : "Это не из‑за города или бюджета: в выдачу попадают только профили с аккаунтом участника (не QA). Можно создать заявку — подберём вручную."}
              </p>
              <p style={{ display: "flex", gap: 8, flexWrap: "wrap", marginTop: 12 }}>
                <Link className="btn" href="/events/new">
                  Создать заявку
                </Link>
                {serviceMode ? (
                  <Link className="btn secondary" href="/search?kind=artist">
                    Смотреть артистов
                  </Link>
                ) : (
                  <a className="btn secondary" href="mailto:hello@bukergo.ru?subject=%D0%9A%D0%B0%D1%82%D0%B0%D0%BB%D0%BE%D0%B3%20%D0%B0%D1%80%D1%82%D0%B8%D1%81%D1%82%D0%BE%D0%B2">
                    Связаться с оператором
                  </a>
                )}
              </p>
            </article>
          ) : null}
          {(!city || city === "Москва") && q.kind !== "artist" && q.kind !== "service" ? <MoscowMap venues={venues} district={q.district || q.metro} /> : null}
          {serviceMode && services.length > 0 ? (
            <div className="grid" data-testid="public-services-grid">
              {services.map((item) => (
                <ServiceResultCard key={item.id} item={item} querySuffix={itemQs || undefined} />
              ))}
            </div>
          ) : null}
          {!serviceMode && items.length > 0 ? (
            <>
              {venues.length > 0 ? <h2 className="catalog-section-title">Артисты</h2> : null}
              <div className="grid">
                {items.map((item) => (
                  <CatalogResultCard
                    key={item.id}
                    item={item}
                    kind="artist"
                    href={`/artists/${item.id}${itemQs ? `?${itemQs}` : ""}`}
                    date={q.date}
                  />
                ))}
              </div>
            </>
          ) : null}
          {!serviceMode && venues.length > 0 ? (
            <>
              {items.length > 0 ? <h2 className="catalog-section-title">Площадки</h2> : null}
              <div className="grid">
                {venues.map((item) => (
                  <CatalogResultCard
                    key={item.id}
                    item={item}
                    kind="venue"
                    href={`/venues/${item.id}${itemQs ? `?${itemQs}` : ""}`}
                    date={q.date}
                  />
                ))}
              </div>
            </>
          ) : null}
        </div>
      </div>
    </main>
  );
}
