"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { CATEGORY, categoryLabel } from "@/lib/copy";
import { moscowToday } from "@/lib/format";
import { trackClientEvent } from "@/lib/api";
import { CityField } from "@/components/CityField";

export type CategoryChip = { code: string; title: string };

export type CatalogFilterValues = {
  city: string;
  date?: string;
  category?: string;
  categories?: CategoryChip[];
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

function fallbackCategories(): CategoryChip[] {
  return Object.entries(CATEGORY).map(([code, title]) => ({ code, title }));
}

function searchHref(base: CatalogFilterValues, cat?: string | null) {
  const p = new URLSearchParams();
  p.set("city", base.city);
  if (base.date) p.set("date", base.date);
  if (cat) p.set("category", cat);
  if (base.event) p.set("event", base.event);
  if (base.requirement) p.set("requirement", base.requirement);
  if (base.exclude) p.set("exclude", base.exclude);
  if (base.kind) p.set("kind", base.kind);
  if (base.format) p.set("format", base.format);
  if (base.travel) p.set("travel", base.travel);
  if (base.budget_max) p.set("budget_max", base.budget_max);
  if (base.guests) p.set("guests", base.guests);
  if (base.seating) p.set("seating", base.seating);
  return `/search?${p.toString()}`;
}

export function CatalogFilters(props: CatalogFilterValues) {
  const {
    city,
    date,
    category,
    categories,
    event,
    requirement,
    exclude,
    kind,
    format,
    travel,
    budget_max,
    guests,
    seating,
  } = props;
  const [open, setOpen] = useState(false);
  // min date only after mount — avoid SSR/client calendar-day drift near midnight.
  const [minDate, setMinDate] = useState<string | undefined>(undefined);
  const [cats, setCats] = useState<CategoryChip[]>(
    categories?.length ? categories : fallbackCategories(),
  );

  useEffect(() => {
    setMinDate(moscowToday());
    const mq = window.matchMedia("(min-width: 900px)");
    const sync = () => setOpen(mq.matches);
    sync();
    mq.addEventListener("change", sync);
    return () => mq.removeEventListener("change", sync);
  }, []);

  useEffect(() => {
    if (categories?.length) {
      setCats(categories);
      return;
    }
    let cancelled = false;
    fetch(`${process.env.NEXT_PUBLIC_API_URL || "/api"}/categories`)
      .then((r) => (r.ok ? r.json() : Promise.reject()))
      .then((data: { items?: { code?: string; title?: string }[] }) => {
        const items = Array.isArray(data.items) ? data.items : [];
        const mapped = items
          .map((c) => ({
            code: String(c.code || ""),
            title: c.title || categoryLabel(c.code),
          }))
          .filter((c) => c.code);
        if (!cancelled && mapped.length) setCats(mapped);
      })
      .catch(() => {
        if (!cancelled) setCats(fallbackCategories());
      });
    return () => {
      cancelled = true;
    };
  }, [categories]);

  const closedLabel = [
    city,
    date || "без даты",
    categoryLabel(category) || (kind === "venue" ? "площадки" : "все"),
    guests ? `от ${guests} гостей` : null,
  ]
    .filter(Boolean)
    .join(" · ");

  return (
    <aside className="filters card surface-glass">
      <button type="button" className="filter-toggle" onClick={() => setOpen((v) => !v)}>
        {open ? "Спрятать фильтр" : closedLabel}
      </button>
      <div className={`filter-body${open ? " open" : ""}`}>
        <h2 className="filter-title">Сузить охоту</h2>
        <form
          action="/search"
          method="get"
          onSubmit={() => {
            trackClientEvent("search.performed", { city, category: category || "all", kind: kind || "all" });
          }}
        >
          <CityField name="city" defaultValue={city} />
          <label>
            Дата
            <input name="date" type="date" min={minDate} defaultValue={date || ""} />
          </label>
          <label>
            Тип
            <select name="kind" defaultValue={kind || ""}>
              <option value="">Артисты и площадки</option>
              <option value="artist">Только исполнители</option>
              <option value="venue">Только площадки</option>
            </select>
          </label>
          <label>
            Формат (исполнитель)
            <input name="format" type="text" placeholder="wedding, club…" defaultValue={format || ""} />
          </label>
          <label>
            Бюджет до, ₽
            <input name="budget_max" type="number" min={0} placeholder="например 80000" defaultValue={budget_max || ""} />
          </label>
          <label>
            Выезд
            <select name="travel" defaultValue={travel || ""}>
              <option value="">Не важно</option>
              <option value="true">Только с выездом</option>
              <option value="false">Без выезда</option>
            </select>
          </label>
          <label>
            Гостей от (зал)
            <input name="guests" type="number" min={1} placeholder="80" defaultValue={guests || ""} />
          </label>
          <label>
            Рассадка / зал (подсказка)
            <input name="seating" type="text" placeholder="банкет, театр…" defaultValue={seating || ""} />
          </label>
          {event ? <input type="hidden" name="event" value={event} /> : null}
          {requirement ? <input type="hidden" name="requirement" value={requirement} /> : null}
          {exclude ? <input type="hidden" name="exclude" value={exclude} /> : null}
          <p className="filter-label">Категория</p>
          <nav className="category-chips" aria-label="Категории">
            <Link
              href={searchHref({ ...props, category: undefined }, null)}
              className={`chip${category ? "" : " on"}`}
              aria-current={category ? undefined : "page"}
            >
              Все
            </Link>
            {cats.map((c) => (
              <Link
                key={c.code}
                href={searchHref(props, c.code)}
                className={`chip${category === c.code ? " on" : ""}`}
                aria-current={category === c.code ? "page" : undefined}
              >
                {c.title || categoryLabel(c.code)}
              </Link>
            ))}
          </nav>
          <p className="timeline">Без слота в расписании сюда не пускаем. Жалко, но честно.</p>
          <button type="submit">Показать живых</button>
        </form>
      </div>
    </aside>
  );
}
