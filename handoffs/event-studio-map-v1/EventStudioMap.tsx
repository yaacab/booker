"use client";

import { useMemo, useState } from "react";
import "./event-studio-map.css";

type Stage = "Основа" | "Место" | "Команда" | "Детали" | "Проверка";
type Role = "Ведущий" | "DJ" | "Фотограф" | "Декоратор";

export type EventStudioDraft = {
  title: string;
  kind: string;
  city: string;
  date: string;
  startsAt: string;
  endsAt: string;
  guests: number;
  venueId?: string;
  talentIds: string[];
  requirements: string[];
};

export type EventStudioMapProps = {
  initialDraft?: Partial<EventStudioDraft>;
  onDraftChange?: (draft: EventStudioDraft) => void;
  onContinue?: (draft: EventStudioDraft) => void;
  onOpenBrief?: () => void;
};

type Talent = {
  id: string;
  name: string;
  role: Role;
  priceFrom: number;
  rating: number;
  reviews: number;
  initials: string;
  tone: string;
};

const stages: Stage[] = ["Основа", "Место", "Команда", "Детали", "Проверка"];
const talents: Talent[] = [
  { id: "host-1", name: "Кирилл Воробьёв", role: "Ведущий", priceFrom: 75000, rating: 4.9, reviews: 47, initials: "КВ", tone: "emerald" },
  { id: "dj-1", name: "DJ Alex Reef", role: "DJ", priceFrom: 60000, rating: 4.8, reviews: 32, initials: "AR", tone: "graphite" },
  { id: "photo-1", name: "Мария Светлова", role: "Фотограф", priceFrom: 52000, rating: 4.9, reviews: 61, initials: "МС", tone: "gold" },
  { id: "decor-1", name: "Студия «Воздух»", role: "Декоратор", priceFrom: 110000, rating: 4.7, reviews: 24, initials: "В", tone: "rose" },
];

const baseDraft: EventStudioDraft = {
  title: "Свадьба Анны и Михаила",
  kind: "Свадьба",
  city: "Москва",
  date: "2025-09-12",
  startsAt: "17:00",
  endsAt: "23:30",
  guests: 80,
  venueId: "house-by-water",
  talentIds: ["host-1", "dj-1", "photo-1"],
  requirements: ["Звук и свет", "Кейтеринг"],
};

const rubles = new Intl.NumberFormat("ru-RU");

function Icon({ name }: { name: "home" | "calendar" | "users" | "place" | "check" | "search" | "plus" | "arrow" }) {
  const paths = {
    home: <><path d="m3 11 9-8 9 8"/><path d="M5 10v10h14V10"/><path d="M9 20v-6h6v6"/></>,
    calendar: <><rect x="3" y="5" width="18" height="16" rx="2"/><path d="M16 3v4M8 3v4M3 10h18"/></>,
    users: <><path d="M16 21v-2a4 4 0 0 0-4-4H6a4 4 0 0 0-4 4v2"/><circle cx="9" cy="7" r="4"/><path d="M22 21v-2a4 4 0 0 0-3-3.87M16 3.13a4 4 0 0 1 0 7.75"/></>,
    place: <><path d="M3 21h18M5 21V6l7-3 7 3v15"/><path d="M9 9h1M14 9h1M9 13h1M14 13h1"/></>,
    check: <path d="m5 12 4 4L19 6"/>,
    search: <><circle cx="11" cy="11" r="7"/><path d="m20 20-4-4"/></>,
    plus: <path d="M12 5v14M5 12h14"/>,
    arrow: <path d="m9 18 6-6-6-6"/>,
  };
  return <svg className="es-icon" viewBox="0 0 24 24" aria-hidden="true">{paths[name]}</svg>;
}

export default function EventStudioMap({ initialDraft, onDraftChange, onContinue, onOpenBrief }: EventStudioMapProps) {
  const [stage, setStage] = useState<Stage>("Команда");
  const [query, setQuery] = useState("");
  const [role, setRole] = useState<Role | "Все">("Все");
  const [draft, setDraft] = useState<EventStudioDraft>({ ...baseDraft, ...initialDraft });

  const selected = talents.filter((item) => draft.talentIds.includes(item.id));
  const filtered = talents.filter((item) => {
    const matchesRole = role === "Все" || item.role === role;
    const haystack = `${item.name} ${item.role}`.toLocaleLowerCase("ru");
    return matchesRole && haystack.includes(query.toLocaleLowerCase("ru"));
  });
  const budget = useMemo(() => selected.reduce((sum, item) => sum + item.priceFrom, 250000), [selected]);

  function update(next: EventStudioDraft) {
    setDraft(next);
    onDraftChange?.(next);
  }

  function toggleTalent(id: string) {
    const talentIds = draft.talentIds.includes(id)
      ? draft.talentIds.filter((talentId) => talentId !== id)
      : [...draft.talentIds, id];
    update({ ...draft, talentIds });
  }

  return (
    <main className="event-studio-shell">
      <header className="event-studio-header">
        <div className="event-studio-brand"><span className="brand-mark">Б</span><strong>Букер</strong></div>
        <div className="event-studio-title"><h1>Соберите событие</h1><span><i /> Автосохранение</span></div>
        <div className="event-studio-actions"><button className="text-button">?&nbsp; Помощь</button><button className="outline-button" onClick={onOpenBrief}>Открыть бриф</button><span className="avatar">АВ</span></div>
      </header>

      <div className="event-studio-grid">
        <aside className="stage-rail" aria-label="Этапы создания события">
          <button className="home-button" aria-label="На главную"><Icon name="home" /></button>
          <ol>
            {stages.map((item, index) => {
              const activeIndex = stages.indexOf(stage);
              const completed = index < activeIndex;
              return <li key={item} className={item === stage ? "active" : completed ? "done" : ""}>
                <button onClick={() => setStage(item)}><span>{completed ? <Icon name="check" /> : index + 1}</span>{item}</button>
              </li>;
            })}
          </ol>
          <button className="collapse-button">← Свернуть</button>
        </aside>

        <section className="event-map" aria-label="Карта события">
          <div className="connection-lines" aria-hidden="true"><i className="line venue-line"/><i className="line time-line"/><i className="line team-line"/><i className="line terms-line"/></div>

          <article className="map-card venue-card">
            <h2><Icon name="place" /> Площадка</h2>
            <div className="venue-visual"><div className="venue-sun"/><div className="venue-building"><i/><i/><i/></div></div>
            <h3>Дом у воды</h3><p>Московская обл., 20 км от МКАД</p>
            <div className="card-meta"><span>80 гостей</span><span>Площадка + банкет</span></div>
            <button className="card-button">Подробнее</button>
          </article>

          <article className="map-card time-card">
            <h2><Icon name="calendar" /> Дата и время</h2>
            <div className="time-row"><strong>12 сентября 2025</strong><small>пятница</small></div>
            <div className="time-row"><strong>17:00 — 23:30</strong><small>6 ч 30 м</small></div>
            <button className="card-button">Изменить</button>
          </article>

          <div className="event-core">
            <span className="event-symbol">◎</span><strong>{draft.title}</strong><small>12 сентября · {draft.city} · {draft.guests} гостей</small>
          </div>

          <article className="map-card team-card">
            <h2><Icon name="users" /> Команда</h2>
            <div className="team-faces">
              {selected.slice(0, 3).map((item) => <span key={item.id} className={`talent-face ${item.tone}`}>{item.initials}</span>)}
              <button className="add-face" onClick={() => setRole("Все")}><Icon name="plus" /></button>
            </div>
            <div className="role-chips">{selected.map((item) => <button key={item.id} onClick={() => toggleTalent(item.id)}>{item.role}</button>)}<button className="ghost-chip">+ Декоратор</button></div>
            <button className="card-button">Смотреть всех</button>
          </article>

          <article className="map-card terms-card">
            <h2>Условия</h2>
            {draft.requirements.map((item) => <div className="requirement" key={item}><span>{item}<small>{item === "Звук и свет" ? "Под ключ" : "Банкет + фуршет"}</small></span><i><Icon name="check" /></i></div>)}
            <button className="card-button">Подробнее</button>
          </article>

          <div className="compatibility-note"><strong>✣&nbsp; Мы анализируем совместимость</strong><span>команды и площадки · около 1 минуты</span></div>

          <div className="event-summary">
            <div><small>Состав</small><strong>{selected.length + 1} из 6</strong><span>Добавьте декоратора<br/>и специалиста по свету</span></div>
            <div><small>Ориентир бюджета</small><strong>{rubles.format(budget)}–{rubles.format(Math.round(budget * 1.28))} ₽</strong><span>Итог — только после<br/>серверных предложений</span></div>
            <button onClick={() => onContinue?.(draft)}>Продолжить <Icon name="arrow" /></button>
          </div>
        </section>

        <aside className="talent-panel" aria-label="Добавить исполнителя">
          <div className="panel-header"><button aria-label="Назад">←</button><h2>Добавить исполнителя</h2><button aria-label="Закрыть">×</button></div>
          <label className="search-box"><Icon name="search"/><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Поиск по имени, роли, стилю…" /></label>
          <div className="panel-filters">
            <button>Свободен 12 сен⌄</button><button>до 120 000 ₽⌄</button><button>Настроить</button>
          </div>
          <div className="role-tabs">
            {(["Все", "Ведущий", "DJ", "Фотограф", "Декоратор"] as const).map((item) => <button key={item} className={role === item ? "selected" : ""} onClick={() => setRole(item)}>{item}</button>)}
          </div>
          <div className="talent-list">
            {filtered.map((item) => {
              const isSelected = draft.talentIds.includes(item.id);
              return <article className="talent-card" key={item.id}>
                <div className={`talent-photo ${item.tone}`}><span>{item.initials}</span></div>
                <div className="talent-copy"><h3>{item.name}</h3><p>{item.role}</p><strong>от {rubles.format(item.priceFrom)} ₽</strong><span className="available">● Свободен 12 сен</span><small>Рейтинг {item.rating} ({item.reviews})</small></div>
                <button className={isSelected ? "remove-talent" : "add-talent"} onClick={() => toggleTalent(item.id)}>{isSelected ? "Убрать из события" : "Добавить в событие"}</button>
              </article>;
            })}
          </div>
        </aside>
      </div>
    </main>
  );
}
