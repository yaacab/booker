"use client";

import { useState } from "react";
import { CityField } from "@/components/CityField";
import { HeroDateField } from "@/components/HeroDateField";

/** Dual search: исполнитель (категория) vs площадка (гости). Spec §4.1 / W1-HOME. */
export function HomeSearchForm() {
  const [kind, setKind] = useState<"artist" | "venue">("artist");

  return (
    <form className="search search-vertical" action="/search" method="get">
      <input type="hidden" name="kind" value={kind} />
      <CityField name="city" defaultValue="Москва" />
      <HeroDateField />
      <fieldset className="home-kind-toggle">
        <legend className="filter-label">Что ищем</legend>
        <div className="category-chips" role="group" aria-label="Тип поиска">
          <button
            type="button"
            className={`chip${kind === "artist" ? " on" : ""}`}
            aria-pressed={kind === "artist"}
            onClick={() => setKind("artist")}
          >
            Исполнитель
          </button>
          <button
            type="button"
            className={`chip${kind === "venue" ? " on" : ""}`}
            aria-pressed={kind === "venue"}
            onClick={() => setKind("venue")}
          >
            Площадка
          </button>
        </div>
      </fieldset>
      {kind === "artist" ? (
        <label>
          Категория
          <select name="category" defaultValue="dj">
            <option value="dj">DJ</option>
            <option value="host">Ведущий</option>
            <option value="cover">Кавер-группа</option>
          </select>
        </label>
      ) : (
        <label>
          Гостей от
          <input name="guests" type="number" min={1} defaultValue={80} />
        </label>
      )}
      <button type="submit">Показать свободных</button>
    </form>
  );
}
