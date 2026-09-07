"use client";

import { useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { CityField } from "@/components/CityField";
import { categoryLabel } from "@/lib/copy";
import { formatDay, guestsLabel, money } from "@/lib/format";
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
  if (status === "conflict") return "Конфликт вкладок · загружена более новая версия";
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
  const [stage, setStage] = useState<StudioStage>("Основа");
  const [query, setQuery] = useState("");
  const [role, setRole] = useState<(typeof ROLE_FILTERS)[number]>("Все");
  const [panelOpen, setPanelOpen] = useState(false);
  const [compactPanel, setCompactPanel] = useState(false);
  const workspaceRef = useRef<HTMLDivElement>(null);
  const [reducedMotion, setReducedMotion] = useState(false);
  const panelRef = useRef<HTMLElement>(null);

  useEffect(() => {
    const media = window.matchMedia("(prefers-reduced-motion: reduce)");
    const updateMotion = () => setReducedMotion(media.matches);
    updateMotion();
    media.addEventListener("change", updateMotion);
    return () => media.removeEventListener("change", updateMotion);
  }, []);

  useEffect(() => {
    const media = window.matchMedia("(max-width: 1180px)");
    const update = () => setCompactPanel(media.matches);
    update();
    media.addEventListener("change", update);
    return () => media.removeEventListener("change", update);
  }, []);

  useEffect(() => {
    if (!panelOpen || !compactPanel) return;
    const previousFocus = document.activeElement as HTMLElement | null;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    workspaceRef.current?.setAttribute("inert", "");
    const frame = requestAnimationFrame(() => panelRef.current?.querySelector<HTMLButtonElement>('button[aria-label="Закрыть панель"]')?.focus({ preventScroll: true }));
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") { event.preventDefault(); setPanelOpen(false); }
      if (event.key !== "Tab") return;
      const controls = Array.from(panelRef.current?.querySelectorAll<HTMLElement>('button:not(:disabled), input:not(:disabled), select:not(:disabled), a[href], [tabindex="0"]') || []).filter(el => el.getClientRects().length > 0);
      const first = controls[0], last = controls[controls.length - 1];
      if (!first) { event.preventDefault(); panelRef.current?.focus(); return; }
      if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last?.focus(); }
      else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first?.focus(); }
    };
    document.addEventListener("keydown", onKey);
    return () => {
      cancelAnimationFrame(frame);
      document.removeEventListener("keydown", onKey);
      document.body.style.overflow = previousOverflow;
      workspaceRef.current?.removeAttribute("inert");
      if (previousFocus?.isConnected && previousFocus.getClientRects().length) previousFocus.focus({ preventScroll: true });
    };
  }, [panelOpen, compactPanel]);

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
  const selectedCount = draft.talentIds.length + (draft.venueId ? 1 : 0);
  const missingTalents = draft.talentIds.filter((id) => !talents.some((item) => item.id === id));

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

  const puzzleSlots = useMemo(() => {
    const selectedTalents = talents.filter((item) => draft.talentIds.includes(item.id));
    return slotsFromDraft({
      date: draft.date,
      dateLabel,
      venueName: venue?.name,
      hasVenue: Boolean(venue),
      talents: selectedTalents.map((item) => ({
        id: item.id,
        roleLabel: item.roleLabel,
        name: item.name,
      })),
    });
  }, [draft.date, draft.talentIds, dateLabel, venue, talents]);

  function goToStage(next: StudioStage) {
    setStage(next);
    const ids: Record<StudioStage, string> = {
      Основа: "studio-basics", Место: "studio-venue", Команда: "studio-team", Детали: "studio-details", Проверка: "studio-summary",
    };
    document.getElementById(ids[next])?.scrollIntoView({ behavior: reducedMotion ? "instant" : "smooth", block: "center" });
  }

  function openCatalog() {
    setPanelOpen(true);
    setStage("Команда");
    if (!compactPanel) panelRef.current?.querySelector<HTMLInputElement>("input")?.focus({ preventScroll: true });
  }

  return (
    <main className={`event-studio-shell${panelOpen ? " panel-open" : ""}`}>
      <div ref={workspaceRef} className="studio-workspace">
        <header className="event-studio-header">
          <a className="event-studio-brand" href="/" aria-label="Букер — на главную">Букер<span aria-hidden="true" /></a>
          <span className="studio-header-caption">Люди. Место. Событие.</span>
          <div className="event-studio-actions">{legacyLink}<a href="/cabinet">Мои события <Icon name="arrow" /></a></div>
        </header>
        <div className="studio-heading">
          <div>
            <p className="studio-eyebrow">События <span>/</span> Новое событие</p>
            <h1>Соберите событие</h1>
            <p>Расскажите о планах и соберите команду — всё начинается с ваших идей.</p>
          </div>
          <span className={`studio-save studio-save-${saveStatus}`} role="status" aria-live="polite">
            <Icon name={saveStatus === "saved" ? "check" : "calendar"} />
            {saveLabel(saveStatus)}
            {saveStatus === "error" && onRetrySave ? <button type="button" className="text-button" onClick={onRetrySave}>Повторить</button> : null}
          </span>
        </div>
        <nav className="stage-rail" aria-label="Этапы создания события">
          <ol>
            {STUDIO_STAGES.map((item, index) => (
              <li key={item} className={item === stage ? "active" : ""}>
                <button type="button" aria-current={item === stage ? "step" : undefined} onClick={() => goToStage(item)}>
                  <span>{index + 1}</span>{item}
                </button>
              </li>
            ))}
          </ol>
        </nav>
        <div className="event-studio-grid">
          <section className="event-map" aria-label="Карта события">
            <article className={`map-card studio-basics${stage === "Основа" ? " map-card-focus" : ""}`} id="studio-basics">
              <div className="studio-section-head"><span className="studio-step">01</span><h2>О событии</h2></div>
              <label htmlFor="event-title">Название события</label>
              <input id="event-title" className="event-core-title" value={draft.title} placeholder="Например, наш летний праздник" onChange={(e) => update({ ...draft, title: e.target.value })} />
              <div className="studio-field-grid">
                <label>Дата события<input id="studio-date" type="date" value={draft.date} onChange={(e) => update({ ...draft, date: e.target.value })} /></label>
                <CityField value={draft.city} onChange={(city) => update({ ...draft, city })} />
                <label>Начало<input type="time" value={draft.startsAt} onChange={(e) => update({ ...draft, startsAt: e.target.value })} /></label>
                <label>Окончание<input type="time" value={draft.endsAt} onChange={(e) => update({ ...draft, endsAt: e.target.value })} /></label>
                <label>Формат<input value={draft.kind} placeholder="Свадьба, вечеринка…" onChange={(e) => update({ ...draft, kind: e.target.value })} /></label>
                <label>Гостей<input type="number" min={1} max={5000} value={draft.guests} onChange={(e) => update({ ...draft, guests: Number(e.target.value) || 0 })} /></label>
              </div>
              <p className="studio-field-note">Время события — московское</p>
            </article>

            <div className="puzzle-stage">
              <div className="studio-puzzle-caption"><span>Собираем вашу команду</span><span aria-hidden="true">↘</span></div>
              <PuzzleBoard slots={puzzleSlots} reducedMotion={reducedMotion} onSlotSelect={(slot) => {
                if (slot.id === "date") { goToStage("Основа"); document.getElementById("studio-date")?.focus({ preventScroll: true }); }
                else if (slot.id === "venue") { goToStage("Место"); document.getElementById("venue-select")?.focus({ preventScroll: true }); }
                else openCatalog();
              }} />
              <p className="puzzle-event-meta">{dateLabel} <span>·</span> {draft.city || "Город не указан"} <span>·</span> {guestsLabel(draft.guests)}</p>
              <small>Нажмите на часть пазла, чтобы выбрать детали</small>
            </div>

            <article id="studio-venue" className={`map-card venue-card${stage === "Место" ? " map-card-focus" : ""}`}>
              <div className="studio-section-head"><span className="studio-step"><Icon name="place" /></span><h2>Место встречи</h2></div>
              <h3>{venue?.name || (draft.venueId ? "Выбранная площадка" : "Где всё случится?")}</h3>
              <p>{venue ? venue.city : draft.venueId ? "Площадка недоступна в текущем каталоге" : "Выберите пространство под ваш формат"}</p>
              {venues.length ? (
                <label className="studio-venue-field">Площадка
                  <select id="venue-select" value={draft.venueId || ""} onChange={(e) => setVenue(e.target.value)}>
                    <option value="">Подберём позже</option>
                    {draft.venueId && !venue ? <option value={draft.venueId}>Ранее выбранная площадка</option> : null}
                    {venues.map((item) => <option key={item.id} value={item.id}>{item.name}{item.availabilityLabel ? ` · ${item.availabilityLabel}` : ""}</option>)}
                  </select>
                </label>
              ) : <button type="button" className="card-button" onClick={onReloadCatalog} disabled={loadingTalents}>{loadingTalents ? "Загружаем…" : "Обновить площадки"}</button>}
              {draft.venueId ? <button type="button" className="text-button studio-remove-venue" onClick={() => setVenue("")}>Убрать площадку</button> : null}
            </article>

            <article id="studio-team" className={`map-card team-card${stage === "Команда" ? " map-card-focus" : ""}`}>
              <div className="studio-section-head"><span className="studio-step"><Icon name="users" /></span><h2>Команда события</h2><span className="studio-count">{draft.talentIds.length}</span></div>
              {selected.length || missingTalents.length ? <ul className="studio-selected-team">
                {selected.map((item) => <li key={item.id}><span className="talent-face talent-initials" aria-hidden="true">{item.initials}</span><span><strong>{item.name}</strong><small>{item.roleLabel}</small></span><button type="button" className="studio-remove" onClick={() => toggleTalent(item.id)} aria-label={`Убрать ${item.name} из события`}>×</button></li>)}
                {missingTalents.map((id) => <li key={id}><span><strong>Выбранный исполнитель</strong><small>Недоступен в текущем каталоге</small></span><button type="button" className="studio-remove" onClick={() => toggleTalent(id)} aria-label="Убрать недоступного исполнителя">×</button></li>)}
              </ul> : <p className="studio-empty-team">Музыка, эмоции, воспоминания.<br />Добавьте людей, которые создадут атмосферу.</p>}
              <button type="button" className="card-button" onClick={openCatalog}><Icon name="plus" /> Добавить исполнителя</button>
            </article>

            <article id="studio-details" className={`map-card terms-card${stage === "Детали" ? " map-card-focus" : ""}`}>
              <div className="studio-section-head"><span className="studio-step">04</span><h2>Важные детали</h2></div>
              <p>Что ещё понадобится на событии?</p>
              <div className="studio-requirements">
                {Array.from(new Set(["Звук и свет", "Кейтеринг", ...draft.requirements])).map((item) => <label key={item}><input type="checkbox" checked={draft.requirements.includes(item)} onChange={() => update({ ...draft, requirements: draft.requirements.includes(item) ? draft.requirements.filter((value) => value !== item) : [...draft.requirements, item] })} /><span>{item}</span></label>)}
              </div>
              <p className="studio-field-note">Детали согласуете с командой в сделке.</p>
            </article>

            <div id="studio-summary" className={`event-summary${stage === "Проверка" ? " map-card-focus" : ""}`}>
              <div className="studio-composition"><small>В вашем событии</small><strong>{selectedCount} {selectedCount === 1 ? "участник" : selectedCount > 1 && selectedCount < 5 ? "участника" : "участников"}</strong><span>Команду можно дополнить позже</span></div>
              <div className="studio-budget"><small>Ориентир бюджета</small><strong className={!budgetHint ? "budget-pending" : ""}>{budgetText}</strong><span>Точную стоимость предложат участники</span></div>
              <button type="button" disabled={submitting} onClick={onContinue}>{submitting ? "Отправляем…" : "Продолжить"}<Icon name="arrow" /></button>
              {submitError ? <p className="submit-error" role="alert">{submitError}</p> : null}
            </div>
          </section>
        </div>
      </div>

      <aside ref={panelRef} tabIndex={-1} className="talent-panel" aria-label="Добавить исполнителя" role={compactPanel && panelOpen ? "dialog" : undefined} aria-modal={compactPanel && panelOpen ? true : undefined}>
        <div className="panel-header"><div><p className="studio-eyebrow">Ваша команда</p><h2>Добавить исполнителя</h2></div><button type="button" aria-label="Закрыть панель" onClick={() => setPanelOpen(false)}>×</button></div>
        <p className="studio-catalog-context">{draft.city || "Все города"} · {dateLabel}</p>
        <label className="search-box"><Icon name="search" /><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Имя или роль" aria-label="Поиск исполнителя" /></label>
        <div className="role-tabs" role="group" aria-label="Фильтр по роли">
          {ROLE_FILTERS.map((item) => <button key={item} type="button" aria-pressed={role === item} className={role === item ? "selected" : ""} onClick={() => setRole(item)}>{item === "Все" ? "Все" : categoryLabel(item) || item}</button>)}
        </div>
        {loadingTalents ? <p className="panel-state" role="status">Загружаем каталог…</p> : null}
        {talentsError ? <p className="panel-state" role="alert">{talentsError} <button type="button" className="text-button" onClick={onReloadCatalog}>Повторить</button></p> : null}
        {!loadingTalents && !talentsError && filtered.length === 0 ? <div className="studio-catalog-empty"><Icon name="search" /><h3>Пока нет подходящих участников</h3><p>Попробуйте другую дату, город или роль.</p>{query || role !== "Все" ? <button type="button" className="card-button" onClick={() => { setQuery(""); setRole("Все"); }}>Сбросить фильтры</button> : null}</div> : null}
        <div className="talent-list">
          {filtered.map((item) => {
            const isSelected = draft.talentIds.includes(item.id);
            return <article className={`talent-card${isSelected ? " is-selected" : ""}`} key={item.id}>
              <div className="talent-photo talent-initials" aria-hidden="true">{item.initials}</div>
              <div className="talent-copy"><h3>{item.name}</h3><p>{item.roleLabel}</p><span className={availabilityClass(item.availability)}>{item.availabilityLabel}</span><small>{item.verified ? "Профиль проверен" : "Профиль не проверен"}</small></div>
              <div className="talent-card-footer"><strong>{item.honorariumFrom != null ? `от ${money(item.honorariumFrom)}` : "Цена по запросу"}</strong><button type="button" className={isSelected ? "remove-talent" : "add-talent"} aria-pressed={isSelected} onClick={() => toggleTalent(item.id)}>{isSelected ? "Убрать" : "Добавить"}<Icon name={isSelected ? "check" : "plus"} /></button></div>
            </article>;
          })}
        </div>
        <p className="studio-catalog-note">Вы выбираете команду. Участники подтвердят дату и условия в предложениях.</p>
      </aside>
      {panelOpen && compactPanel ? <button type="button" className="panel-backdrop" aria-label="Закрыть каталог исполнителей" onClick={() => setPanelOpen(false)} /> : null}
      <button type="button" className="mobile-panel-toggle" aria-expanded={panelOpen} onClick={openCatalog}><Icon name="plus" /> Добавить исполнителя</button>
    </main>
  );
}
