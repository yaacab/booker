"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { MOSCOW_DISTRICTS, MOSCOW_METRO } from "@/lib/moscowDistricts";
import { CATEGORY, categoryLabel } from "@/lib/copy";
import { trackClientEvent } from "@/lib/api";

export type CategoryChip = { code: string; title: string };

export type CatalogFilterValues = {
  city: string;
  district?: string;
  metro?: string;
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

  const closedLabel = [
    city,
    date || "без даты",
    categoryLabel(category) || (kind === "venue" ? "площадки" : "все"),
    guests ? `от ${guests} гостей` : null,
  ]
    .filter(Boolean)
    .join(" · ");

  const reset = new URLSearchParams({ city });
  if (event) reset.set("event", event);
  if (requirement) reset.set("requirement", requirement);
  if (exclude) reset.set("exclude", exclude);

  return (
    <aside className="filters catalog-filters">
      <button type="button" className="filter-toggle" aria-expanded={open} aria-controls="catalog-filter-body" onClick={() => setOpen((v) => !v)}>
        <span>Фильтры <span className="catalog-filter-summary">{closedLabel}</span></span>
        <span aria-hidden="true">{open ? "−" : "+"}</span>
      </button>
      <div id="catalog-filter-body" className={`filter-body${open ? " open" : ""}`}>
        <form
          action="/search"
          method="get"
          onSubmit={(event) => {
            const values = new FormData(event.currentTarget);
            trackClientEvent("search.performed", {
              city: String(values.get("city") || city),
              category: String(values.get("category") || "all"),
              kind: String(values.get("kind") || "all"),
            });
          }}
        >
          <input type="hidden" name="city" value={city} />
          {date ? <input type="hidden" name="date" value={date} /> : null}
          {kind ? <input type="hidden" name="kind" value={kind} /> : null}
          {event ? <input type="hidden" name="event" value={event} /> : null}
          {requirement ? <input type="hidden" name="requirement" value={requirement} /> : null}
          {exclude ? <input type="hidden" name="exclude" value={exclude} /> : null}

          <fieldset className="catalog-filter-group"><legend>Район и метро Москвы</legend><datalist id="catalog-districts">{MOSCOW_DISTRICTS.map(x=><option key={x} value={x}/>)}</datalist><datalist id="catalog-metro">{MOSCOW_METRO.map(x=><option key={x} value={x}/>)}</datalist><label>Район<input list="catalog-districts" name="district" defaultValue={props.district || ""} placeholder="Например, Хамовники" maxLength={128}/></label><label>Метро<input list="catalog-metro" name="metro" defaultValue={props.metro || ""} placeholder="Например, Парк культуры" maxLength={128}/></label><p className="timeline">Фильтр расположения применяется к площадкам. Выезд специалиста согласуется отдельно.</p></fieldset>
          <fieldset className="catalog-filter-group catalog-category-options">
            <legend>Категории</legend>
            <label className="catalog-filter-option">
              <input type="radio" name="category" value="" defaultChecked={!category} onChange={(e) => e.currentTarget.form?.requestSubmit()} />
              <span>Все категории</span>
            </label>
            {cats.map((c) => (
              <label key={c.code} className="catalog-filter-option">
                <input type="radio" name="category" value={c.code} defaultChecked={category === c.code} onChange={(e) => e.currentTarget.form?.requestSubmit()} />
                <span>{c.title || categoryLabel(c.code)}</span>
              </label>
            ))}
            {category && !cats.some((c) => c.code === category) ? <label className="catalog-filter-option"><input type="radio" name="category" value={category} defaultChecked /><span>{categoryLabel(category)}</span></label> : null}
          </fieldset>
          <fieldset className="catalog-filter-group">
            <legend>Бюджет, ₽</legend>
            <label className="catalog-budget-input">
              <span>До</span>
              <input aria-label="Бюджет до, ₽" name="budget_max" type="number" min={0} placeholder="Любой бюджет" defaultValue={budget_max || ""} />
            </label>
          </fieldset>
          <fieldset className="catalog-filter-group">
            <legend>Выезд за город</legend>
            {[{ value: "", label: "Не важно" }, { value: "false", label: "Только по городу" }, { value: "true", label: "Готовы выезжать" }].map((choice) => (
              <label key={choice.value} className="catalog-filter-option">
                <input type="radio" name="travel" value={choice.value} defaultChecked={(travel || "") === choice.value} />
                <span>{choice.label}</span>
              </label>
            ))}
          </fieldset>
          <fieldset className="catalog-filter-group catalog-additional-filters">
            <legend>Для вашего события</legend>
            <label>
              Формат (исполнитель)
              <input name="format" type="text" placeholder="wedding, club…" defaultValue={format || ""} />
            </label>
            <label>
              Гостей от (зал)
              <input name="guests" type="number" min={1} placeholder="Любое количество" defaultValue={guests || ""} />
            </label>
            <label>
              Рассадка
              <input name="seating" type="text" placeholder="Банкет, театр…" defaultValue={seating || ""} />
            </label>
          </fieldset>
          <button type="submit" className="catalog-apply-filters">Показать варианты</button>
          <Link className="catalog-reset-filters" href={`/search?${reset.toString()}`}><span aria-hidden="true">↺</span> Сбросить фильтры</Link>
          <p className="timeline catalog-filter-note">Доступность и условия подтверждаются перед бронированием.</p>
        </form>
      </div>
    </aside>
  );
}
