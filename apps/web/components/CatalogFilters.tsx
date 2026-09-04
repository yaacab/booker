"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { CATEGORY, categoryLabel } from "@/lib/copy";
import { moscowToday } from "@/lib/format";
import { trackClientEvent } from "@/lib/api";
import { CityField } from "@/components/CityField";

export type CategoryChip = { code: string; title: string };

function fallbackCategories(): CategoryChip[] {
  return Object.entries(CATEGORY).map(([code, title]) => ({ code, title }));
}

function searchHref(
  city: string,
  date?: string,
  cat?: string,
  event?: string,
  requirement?: string,
  exclude?: string,
) {
  const p = new URLSearchParams();
  p.set("city", city);
  if (date) p.set("date", date);
  if (cat) p.set("category", cat);
  if (event) p.set("event", event);
  if (requirement) p.set("requirement", requirement);
  if (exclude) p.set("exclude", exclude);
  return `/search?${p.toString()}`;
}

export function CatalogFilters({
  city,
  date,
  category,
  categories,
  event,
  requirement,
  exclude,
}: {
  city: string;
  date?: string;
  category?: string;
  categories?: CategoryChip[];
  event?: string;
  requirement?: string;
  exclude?: string;
}) {
  const [open, setOpen] = useState(false);
  const [cats, setCats] = useState<CategoryChip[]>(
    categories?.length ? categories : fallbackCategories(),
  );

  useEffect(() => {
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

  const closedLabel = [city, date || "без даты", categoryLabel(category) || "все"].join(" · ");

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
            trackClientEvent("search.performed", { city, category: category || "all" });
          }}
        >
          <CityField name="city" defaultValue={city} />
          <label>
            Дата
            <input name="date" type="date" min={moscowToday()} defaultValue={date || ""} />
          </label>
          {category ? <input type="hidden" name="category" value={category} /> : null}
          {event ? <input type="hidden" name="event" value={event} /> : null}
          {requirement ? <input type="hidden" name="requirement" value={requirement} /> : null}
          {exclude ? <input type="hidden" name="exclude" value={exclude} /> : null}
          <p className="filter-label">Категория</p>
          <nav className="category-chips" aria-label="Категории">
            <Link
              href={searchHref(city, date, undefined, event, requirement, exclude)}
              className={`chip${category ? "" : " on"}`}
              aria-current={category ? undefined : "page"}
            >
              Все
            </Link>
            {cats.map((c) => (
              <Link
                key={c.code}
                href={searchHref(city, date, c.code, event, requirement, exclude)}
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
