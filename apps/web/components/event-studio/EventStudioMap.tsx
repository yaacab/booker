"use client";

import { useEffect, useMemo, useState, type ReactNode } from "react";
import { CityField } from "@/components/CityField";
import { categoryLabel } from "@/lib/copy";
import { formatDay, money } from "@/lib/format";
import type {
  BudgetHint,
  EventStudioDraft,
  SaveStatus,
  StudioStage,
  TalentItem,
  VenueItem,
} from "./types";
import { STUDIO_STAGES } from "./types";
import PuzzleBoard, { slotsFromDraft } from "./PuzzleBoard";
import "./event-studio-map.css";

type IconName = "home" | "calendar" | "users" | "place" | "check" | "search" | "plus" | "arrow";

export type EventStudioMapProps = {
  draft: EventStudioDraft;
  onDraftChange: (draft: EventStudioDraft) => void;
  talents: TalentItem[];
  venues: VenueItem[];
  budgetHint: BudgetHint | null;
  loadingTalents: boolean;
  talentsError: string | null;
  saveStatus: SaveStatus;
  onRetrySave?: () => void;
  onReloadCatalog?: () => void;
  onContinue: () => void;
  submitting: boolean;
  submitError: string | null;
  legacyLink?: ReactNode;
};

const ROLE_FILTERS = ["Все", "host", "dj", "photo", "decor"] as const;

function Icon({ name }: { name: IconName }) {
  const paths: Record<IconName, ReactNode> = {
    home: (
      <>
        <path d="m3 11 9-8 9 8" />
        <path d="M5 10v10h14V10" />
        <path d="M9 20v-6h6v6" />
      </>
    ),
    calendar: (
      <>
        <rect x="3" y="5" width="18" height="16" rx="2" />
        <path d="M16 3v4M8 3v4M3 10h18" />
      </>
    ),
    users: (
      <>
        <path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2" />
        <circle cx="9" cy="7" r="4" />
        <path d="M22 21v-2a4 4 0 0 0-3-3.87M16 3.13a4 4 0 0 1 0 7.75" />
      </>
    ),
    place: (
      <>
        <path d="M3 21h18M5 21V6l7-3 7 3v15" />
        <path d="M9 9h1M14 9h1M9 13h1M14 13h1" />
      </>
    ),
    check: <path d="m5 12 4 4L19 6" />,
    search: (
      <>
        <circle cx="11" cy="11" r="7" />
        <path d="m20 20-4-4" />
      </>
    ),
    plus: <path d="M12 5v14M5 12h14" />,
    arrow: <path d="m9 18 6-6-6-6" />,
  };
  return (
    <svg className="es-icon" viewBox="0 0 24 24" aria-hidden="true">
      {paths[name]}
    </svg>
  );
}

function saveLabel(status: SaveStatus): string {
  if (status === "offline") return "Без сети · черновик на устройстве";
  if (status === "saving") return "Сохраняем…";
  if (status === "error") return "Ошибка сохранения";
  return "Сохранено автоматически";
}

function availabilityClass(state: TalentItem["availability"]): string {
  return `availability availability-${state}`;
}

export default function EventStudioMap({
  draft,
  onDraftChange,
  talents,
  venues,
  budgetHint,
  loadingTalents,
  talentsError,
  saveStatus,
  onRetrySave,
  onReloadCatalog,
  onContinue,
  submitting,
  submitError,
  legacyLink,
}: EventStudioMapProps) {
  const [stage, setStage] = useState<StudioStage>("Команда");
  const [query, setQuery] = useState("");
  const [role, setRole] = useState<(typeof ROLE_FILTERS)[number]>("Все");
  const [panelOpen, setPanelOpen] = useState(false);
  const [editingTime, setEditingTime] = useState(false);
  const [editingVenue, setEditingVenue] = useState(false);
  const [reducedMotion, setReducedMotion] = useState(false);

  useEffect(() => {
    setReducedMotion(window.matchMedia("(prefers-reduced-motion: reduce)").matches);
  }, []);

  const selected = talents.filter((item) => draft.talentIds.includes(item.id));
  const venue = venues.find((item) => item.id === draft.venueId);
  const filtered = talents.filter((item) => {
    const matchesRole = role === "Все" || item.categoryCode === role;
    const haystack = `${item.name} ${item.roleLabel}`.toLocaleLowerCase("ru");
    return matchesRole && haystack.includes(query.toLocaleLowerCase("ru"));
  });

  const dateLabel = draft.date
    ? formatDay(`${draft.date}T12:00:00+03:00`)
    : "дата позже";
  const positionsTotal = Math.max(selected.length + (venue ? 1 : 0) + 2, 4);

  function update(next: EventStudioDraft) {
    onDraftChange(next);
  }

  function toggleTalent(id: string) {
    const talentIds = draft.talentIds.includes(id)
      ? draft.talentIds.filter((talentId) => talentId !== id)
      : [...draft.talentIds, id];
    update({ ...draft, talentIds });
  }

  function setVenue(id: string) {
    update({ ...draft, venueId: id });
  }

  const budgetText = useMemo(() => {
    if (!budgetHint) return "уточним после предложений";
    return `${money(budgetHint.minRub).replace(" ₽", "")}–${money(budgetHint.maxRub)}`;
  }, [budgetHint]);

  const puzzleSlots = useMemo(
    () =>
      slotsFromDraft({
        date: draft.date,
        dateLabel,
        venueName: venue?.name,
        hasVenue: Boolean(venue),
        talents: selected.map((item) => ({
          id: item.id,
          roleLabel: item.roleLabel,
          name: item.name,
        })),
      }),
    [draft.date, dateLabel, venue, selected],
  );

  return (
    <main className={`event-studio-shell${panelOpen ? " panel-open" : ""}`}>
      <header className="event-studio-header">
        <div className="event-studio-brand">
          <span className="brand-mark">Б</span>
          <strong>Букер</strong>
        </div>
        <div className="event-studio-title">
          <h1>Соберите событие</h1>
          <span role="status" aria-live="polite">
            <i aria-hidden="true" /> {saveLabel(saveStatus)}
            {saveStatus === "error" && onRetrySave ? (
              <button type="button" className="text-button" onClick={onRetrySave}>
                Повторить
              </button>
            ) : null}
          </span>
        </div>
        <div className="event-studio-actions">
          {legacyLink}
          <span className="avatar" aria-hidden="true">
            Б
          </span>
        </div>
      </header>

      <div className="event-studio-grid">
        <aside className="stage-rail" aria-label="Этапы создания события">
          <a className="home-button" href="/" aria-label="На главную">
            <Icon name="home" />
          </a>
          <ol>
            {STUDIO_STAGES.map((item, index) => {
              const activeIndex = STUDIO_STAGES.indexOf(stage);
              const completed = index < activeIndex;
              return (
                <li key={item} className={item === stage ? "active" : completed ? "done" : ""}>
                  <button type="button" onClick={() => setStage(item)}>
                    <span>{completed ? <Icon name="check" /> : index + 1}</span>
                    {item}
                  </button>
                </li>
              );
            })}
          </ol>
        </aside>

        <section className="event-map" aria-label="Карта события">
          <div className="connection-lines" aria-hidden="true">
            <i className="line venue-line" />
            <i className="line time-line" />
            <i className="line team-line" />
            <i className="line terms-line" />
          </div>

          <div className={`puzzle-stage${stage === "Основа" || stage === "Команда" || stage === "Место" ? " map-card-focus" : ""}`}>
            <PuzzleBoard slots={puzzleSlots} reducedMotion={reducedMotion} />
            <div className="puzzle-event-meta">
              <label className="sr-only" htmlFor="event-title">
                Название события
              </label>
              <input
                id="event-title"
                className="event-core-title"
                value={draft.title}
                placeholder="Название события"
                onChange={(e) => update({ ...draft, title: e.target.value })}
              />
              <small>
                {dateLabel} · {draft.city || "город"} · {draft.guests} гостей
              </small>
              <label className="field-inline guests-field">
                Гостей
                <input
                  type="number"
                  min={1}
                  max={5000}
                  value={draft.guests}
                  onChange={(e) => update({ ...draft, guests: Number(e.target.value) || 0 })}
                />
              </label>
            </div>
          </div>

          <article className={`map-card venue-card${stage === "Место" ? " map-card-focus" : ""}`}>
            <h2>
              <Icon name="place" /> Площадка
            </h2>
            <div className="venue-visual" role="img" aria-label="Загородная площадка у воды" />
            <h3>{venue?.name || "Площадка не выбрана"}</h3>
            <p>{venue ? `${venue.city}` : "Можно выбрать позже"}</p>
            <div className="card-meta">
              <span>{draft.guests} гостей</span>
              <span>{venue ? "из каталога" : "подбор позже"}</span>
            </div>
            {venues.length && editingVenue ? (
              <label className="sr-only" htmlFor="venue-select">
                Площадка
              </label>
            ) : null}
            {venues.length && editingVenue ? (
              <select
                id="venue-select"
                className="card-button"
                value={draft.venueId || ""}
                onChange={(e) => {
                  setVenue(e.target.value);
                  setEditingVenue(false);
                }}
              >
                <option value="">Выберите площадку</option>
                {venues.map((item) => (
                  <option key={item.id} value={item.id}>
                    {item.name}
                    {item.availabilityLabel ? ` · ${item.availabilityLabel}` : ""}
                  </option>
                ))}
              </select>
            ) : venues.length ? (
              <button type="button" className="card-button" onClick={() => setEditingVenue(true)}>
                {venue ? "Изменить" : "Выбрать площадку"}
              </button>
            ) : (
              <button type="button" className="card-button" onClick={onReloadCatalog}>
                Обновить каталог
              </button>
            )}
          </article>

          <article className={`map-card time-card${stage === "Основа" ? " map-card-focus" : ""}`}>
            <h2>
              <Icon name="calendar" /> Дата и время
            </h2>
            <div className="time-row">
              <strong>{dateLabel}</strong>
              <small>{draft.city || "город позже"}</small>
            </div>
            <div className="time-row">
              <strong>
                {draft.startsAt} — {draft.endsAt}
              </strong>
              <small>Europe/Moscow</small>
            </div>
            {editingTime ? (
              <div className="time-editor">
                <label className="field-inline">
                  Дата
                  <input type="date" value={draft.date} onChange={(e) => update({ ...draft, date: e.target.value })} />
                </label>
                <label className="field-inline">
                  Начало
                  <input type="time" value={draft.startsAt} onChange={(e) => update({ ...draft, startsAt: e.target.value })} />
                </label>
                <label className="field-inline">
                  Конец
                  <input type="time" value={draft.endsAt} onChange={(e) => update({ ...draft, endsAt: e.target.value })} />
                </label>
                <CityField value={draft.city} onChange={(city) => update({ ...draft, city })} />
                <button type="button" className="card-button" onClick={() => setEditingTime(false)}>Готово</button>
              </div>
            ) : (
              <button type="button" className="card-button" onClick={() => setEditingTime(true)}>Изменить</button>
            )}
          </article>

          <article className={`map-card team-card${stage === "Команда" ? " map-card-focus" : ""}`}>
            <h2>
              <Icon name="users" /> Команда
            </h2>
            <div className="team-faces">
              {selected.slice(0, 3).map((item, index) => (
                <span key={item.id} className={`talent-face reference-portrait portrait-${index % 3}`} title={item.name}>
                  <span className="sr-only">{item.name}</span>
                </span>
              ))}
              <button type="button" className="add-face" aria-label="Добавить исполнителя" onClick={() => setPanelOpen(true)}>
                <Icon name="plus" />
              </button>
            </div>
            <div className="role-chips">
              {selected.map((item) => (
                <button key={item.id} type="button" onClick={() => toggleTalent(item.id)}>
                  {item.roleLabel}
                </button>
              ))}
              <button type="button" className="ghost-chip" onClick={() => setPanelOpen(true)}>
                + Добавить
              </button>
            </div>
            <button type="button" className="card-button" onClick={() => setPanelOpen(true)}>
              Смотреть всех
            </button>
          </article>

          <article className={`map-card terms-card${stage === "Детали" ? " map-card-focus" : ""}`}>
            <h2>Условия</h2>
            {draft.requirements.map((item) => (
              <div className="requirement" key={item}>
                <span>
                  {item}
                  <small>Уточняется в Deal Room</small>
                </span>
                <i aria-hidden="true">
                  <Icon name="check" />
                </i>
              </div>
            ))}
          </article>

          <div className="compatibility-note" role="note">
            <strong>✣ Мы анализируем совместимость</strong>
            <span>команды и площадки · данные из каталога</span>
          </div>

          <div className={`event-summary${stage === "Проверка" ? " map-card-focus" : ""}`}>
            <div>
              <small>Состав</small>
              <strong>
                {selected.length + (venue ? 1 : 0)} из {positionsTotal}
              </strong>
              <span>
                {selected.length ? "Можно добавить ещё роли" : "Добавьте исполнителей"}
              </span>
            </div>
            <div>
              <small>Ориентир бюджета</small>
              <strong>{budgetText}</strong>
              <span>
                Итог — только после
                <br />
                серверных предложений
              </span>
            </div>
            {submitError ? (
              <p className="submit-error" role="alert">
                {submitError}
              </p>
            ) : null}
            <button type="button" disabled={submitting} onClick={onContinue}>
              {submitting ? "Отправляем…" : "Продолжить"} <Icon name="arrow" />
            </button>
          </div>
        </section>

        <aside className="talent-panel" aria-label="Добавить исполнителя">
          <div className="panel-header">
            <button type="button" aria-label="Назад" onClick={() => setPanelOpen(false)}>
              ←
            </button>
            <h2>Добавить исполнителя</h2>
            <button type="button" aria-label="Закрыть панель" onClick={() => setPanelOpen(false)}>
              ×
            </button>
          </div>
          <label className="search-box">
            <Icon name="search" />
            <input
              value={query}
              onChange={(event) => setQuery(event.target.value)}
              placeholder="Поиск по имени, роли, стилю…"
              aria-label="Поиск исполнителя"
            />
          </label>
          <div className="role-tabs" role="tablist" aria-label="Фильтр по роли">
            {ROLE_FILTERS.map((item) => (
              <button
                key={item}
                type="button"
                role="tab"
                aria-selected={role === item}
                className={role === item ? "selected" : ""}
                onClick={() => setRole(item)}
              >
                {item === "Все" ? "Все" : categoryLabel(item) || item}
              </button>
            ))}
          </div>
          {loadingTalents ? <p className="panel-state">Загружаем каталог…</p> : null}
          {talentsError ? (
            <p className="panel-state" role="alert">
              {talentsError}{" "}
              <button type="button" className="text-button" onClick={onReloadCatalog}>
                Повторить
              </button>
            </p>
          ) : null}
          {!loadingTalents && !talentsError && filtered.length === 0 ? (
            <p className="panel-state">Никого не нашли — попробуйте другую дату или роль.</p>
          ) : null}
          <div className="talent-list">
            {filtered.map((item, index) => {
              const isSelected = draft.talentIds.includes(item.id);
              return (
                <article className="talent-card" key={item.id}>
                  <div className={`talent-photo reference-portrait portrait-${index % 3}`} role="img" aria-label={`Фото: ${item.name}`}>
                    <span className="sr-only">{item.initials}</span>
                  </div>
                  <div className="talent-copy">
                    <h3>{item.name}</h3>
                    <p>{item.roleLabel}</p>
                    {item.honorariumFrom != null ? (
                      <strong>от {money(item.honorariumFrom).replace(" ₽", "")} ₽</strong>
                    ) : (
                      <strong>цена после предложения</strong>
                    )}
                    <span className={availabilityClass(item.availability)}>{item.availabilityLabel}</span>
                    <small>{item.verified ? "Верифицирован" : "Нужна проверка"}</small>
                  </div>
                  <button
                    type="button"
                    className={isSelected ? "remove-talent" : "add-talent"}
                    onClick={() => toggleTalent(item.id)}
                  >
                    {isSelected ? "Убрать из события" : "Добавить в событие"}
                  </button>
                </article>
              );
            })}
          </div>
        </aside>
      </div>

      {panelOpen ? (
        <button type="button" className="panel-backdrop" aria-label="Закрыть каталог исполнителей" onClick={() => setPanelOpen(false)} />
      ) : null}

      <button
        type="button"
        className="mobile-panel-toggle"
        aria-expanded={panelOpen}
        onClick={() => setPanelOpen((value) => !value)}
      >
        {panelOpen ? "Свернуть каталог" : "Добавить исполнителя"}
      </button>

      {!reducedMotion ? null : (
        <style>{`.event-studio-shell * { transition: none !important; animation: none !important; }`}</style>
      )}
    </main>
  );
}
