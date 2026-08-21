"use client";

import { useEffect, useState } from "react";
import { categoryLabel } from "@/lib/copy";
import { moscowToday } from "@/lib/format";
import { CityField } from "@/components/CityField";

export function CatalogFilters({
  city,
  date,
  category,
}: {
  city: string;
  date?: string;
  category?: string;
}) {
  const [open, setOpen] = useState(false);

  useEffect(() => {
    const mq = window.matchMedia("(min-width: 900px)");
    const sync = () => setOpen(mq.matches);
    sync();
    mq.addEventListener("change", sync);
    return () => mq.removeEventListener("change", sync);
  }, []);

  const closedLabel = [city, date || "без даты", categoryLabel(category) || "все"].join(" · ");

  return (
    <aside className="filters card">
      <button type="button" className="filter-toggle" onClick={() => setOpen((v) => !v)}>
        {open ? "Спрятать фильтр" : closedLabel}
      </button>
      <div className={`filter-body${open ? " open" : ""}`}>
        <h2 className="filter-title">Сузить охоту</h2>
        <form action="/search" method="get">
          <CityField name="city" defaultValue={city} />
          <label>
            Дата
            <input name="date" type="date" min={moscowToday()} defaultValue={date || ""} />
          </label>
          <label>
            Категория
            <select name="category" defaultValue={category || ""}>
              <option value="">Все</option>
              <option value="dj">DJ</option>
              <option value="host">Ведущий</option>
              <option value="cover">Кавер</option>
              <option value="venue">Площадка</option>
            </select>
          </label>
          <p className="timeline">Без слота в расписании сюда не пускаем. Жалко, но честно.</p>
          <button type="submit">Показать живых</button>
        </form>
      </div>
    </aside>
  );
}
