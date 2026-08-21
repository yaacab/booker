"use client";

import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { api, getToken } from "@/lib/api";
import { CityField } from "@/components/CityField";
import { moscowToday } from "@/lib/format";
import { loginHref } from "@/lib/next";

const STEPS = [
  { id: "what", q: "Формат события", hint: "Выберите базовый сценарий — детали можно изменить позже.", unknown: false },
  { id: "when", q: "Дата и город", hint: "По этим данным каталог проверит доступные слоты.", unknown: false },
  { id: "guests", q: "Количество гостей", hint: "Нужно для подбора формата площадки и требований райдера.", unknown: false },
  { id: "artist", q: "Состав команды", hint: "Добавьте несколько ролей. Конкретных исполнителей подберём по общей доступности даты.", unknown: true },
  { id: "venue", q: "Площадка", hint: "Укажите, есть ли площадка или её нужно подобрать.", unknown: true },
  { id: "tech", q: "Технические условия", hint: "Отметьте текущее состояние — точный райдер согласуется в Deal Room.", unknown: true },
  { id: "budget", q: "Бюджет", hint: "Диапазон помогает отфильтровать варианты, но не рассчитывает итоговую цену.", unknown: true },
  { id: "check", q: "Проверка заявки", hint: "Проверьте данные перед отправкой. Итоговая сумма появится только в серверном предложении.", unknown: false },
] as const;

const TEAM_ROLES = [
  { id: "host", label: "Ведущий", mark: "В", group: "Программа", description: "Ведёт сценарий и взаимодействует с гостями" },
  { id: "dj", label: "DJ", mark: "DJ", group: "Программа", description: "Музыкальное сопровождение и танцевальный блок" },
  { id: "vocal", label: "Вокалист", mark: "VO", group: "Артисты", description: "Сольная программа или отдельные выходы" },
  { id: "cover", label: "Кавер-группа", mark: "CG", group: "Артисты", description: "Живой сет полным составом" },
  { id: "musician", label: "Музыкант", mark: "MU", group: "Артисты", description: "Саксофон, гитара, перкуссия и другие инструменты" },
  { id: "dance", label: "Танцевальное шоу", mark: "DS", group: "Шоу", description: "Один или несколько танцевальных номеров" },
  { id: "show", label: "Шоу-программа", mark: "SH", group: "Шоу", description: "Иллюзионист, стендап или специальный номер" },
  { id: "photo", label: "Фотограф", mark: "PH", group: "Медиа", description: "Репортажная и постановочная съёмка" },
  { id: "video", label: "Видеограф", mark: "VI", group: "Медиа", description: "Видео события и монтаж" },
  { id: "sound", label: "Звукорежиссёр", mark: "AU", group: "Продакшен", description: "Звук, микрофоны и техническая координация" },
  { id: "light", label: "Светорежиссёр", mark: "LX", group: "Продакшен", description: "Световая схема и управление во время программы" },
] as const;

const TEAM_PRESETS = [
  { id: "base", title: "Ведущий + DJ", description: "Базовая программа события", roles: { host: 1, dj: 1 } },
  { id: "live", title: "Живой концерт", description: "Вокал и живое сопровождение", roles: { vocal: 1, musician: 2, sound: 1 } },
  { id: "media", title: "Событие под ключ", description: "Программа и медиакоманда", roles: { host: 1, dj: 1, photo: 1, video: 1 } },
  { id: "show", title: "Большое шоу", description: "Сцена, артисты и продакшен", roles: { cover: 1, dance: 4, sound: 1, light: 1 } },
] as const;

type Draft = {
  what: string;
  city: string;
  date: string;
  guests: string;
  artist: string;
  team: Record<string, number>;
  customTeam: string[];
  venue: string;
  tech: string;
  budget: string;
};

const EMPTY: Draft = {
  what: "Свадьба",
  city: "Москва",
  date: "",
  guests: "80",
  artist: "dj",
  team: { dj: 1 },
  customTeam: [],
  venue: "unknown",
  tech: "unknown",
  budget: "",
};

const DRAFT_KEY = "booker.eventDraft";

export default function NewEventPage() {
  const router = useRouter();
  const [step, setStep] = useState(0);
  const [draft, setDraft] = useState<Draft>(EMPTY);
  const [error, setError] = useState("");
  const [unknown, setUnknown] = useState<Record<string, boolean>>({});
  const [hydrated, setHydrated] = useState(false);
  const [saving, setSaving] = useState(false);
  const [roofName, setRoofName] = useState("");
  const [saveStatus, setSaveStatus] = useState<"saving" | "saved" | "offline">("saved");
  const [previewOpen, setPreviewOpen] = useState(false);
  const [online, setOnline] = useState(true);
  const [customRole, setCustomRole] = useState("");

  useEffect(() => {
    try {
      const raw = localStorage.getItem(DRAFT_KEY);
      if (raw) {
        const saved = JSON.parse(raw) as {
          draft?: Partial<Draft>;
          unknown?: Record<string, boolean>;
          step?: number;
          roofName?: string;
        };
        if (saved.draft) {
          const restored = { ...EMPTY, ...saved.draft };
          if (!saved.draft.team && saved.draft.artist && saved.draft.artist !== "unknown") {
            restored.team = { [saved.draft.artist]: 1 };
          }
          setDraft(restored);
        }
        if (saved.unknown) setUnknown(saved.unknown);
        if (typeof saved.step === "number") setStep(Math.min(STEPS.length - 1, Math.max(0, saved.step)));
        if (saved.roofName) setRoofName(saved.roofName);
      }
    } catch {
      /* ignore */
    }
    const q = new URLSearchParams(window.location.search);
    const venue = q.get("venue");
    const roof = q.get("roof");
    if (venue === "need" || venue === "own" || venue === "unknown") {
      setDraft((d) => ({ ...d, venue }));
      setUnknown((u) => ({ ...u, venue: venue === "unknown" }));
    }
    if (roof) {
      setRoofName(roof);
      setDraft((d) => ({ ...d, venue: "need" }));
      setUnknown((u) => ({ ...u, venue: false }));
    }
    setHydrated(true);
  }, []);

  useEffect(() => {
    const sync = () => {
      const nextOnline = navigator.onLine;
      setOnline(nextOnline);
      setSaveStatus(nextOnline ? "saved" : "offline");
    };
    sync();
    window.addEventListener("online", sync);
    window.addEventListener("offline", sync);
    return () => {
      window.removeEventListener("online", sync);
      window.removeEventListener("offline", sync);
    };
  }, []);

  useEffect(() => {
    document.querySelector<HTMLButtonElement>(".steps button.active")?.scrollIntoView({
      inline: "center",
      block: "nearest",
      behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth",
    });
  }, [step]);

  useEffect(() => {
    if (!hydrated) return;
    setSaveStatus(navigator.onLine ? "saving" : "offline");
    const timer = window.setTimeout(() => {
      localStorage.setItem(DRAFT_KEY, JSON.stringify({ draft, unknown, step, roofName, savedAt: new Date().toISOString() }));
      setSaveStatus(navigator.onLine ? "saved" : "offline");
    }, 450);
    return () => window.clearTimeout(timer);
  }, [draft, unknown, step, roofName, hydrated]);

  const preview = useMemo(() => {
    const artist = unknown.artist
      ? "состав подберёт оператор"
      : [...TEAM_ROLES.filter((role) => (draft.team[role.id] || 0) > 0).map((role) => `${role.label}${draft.team[role.id] > 1 ? ` ×${draft.team[role.id]}` : ""}`), ...draft.customTeam]
          .join(", ") || "состав не выбран";
    const venue =
      draft.venue === "unknown" || unknown.venue
        ? "площадка не выбрана"
        : roofName
          ? `смотрим: ${roofName}`
          : draft.venue === "need"
            ? "площадку ищем"
            : "площадка своя";
    return [
      draft.what || "формат не указан",
      draft.city,
      draft.date || "дата позже",
      `${draft.guests || "?"} гостей`,
      artist,
      venue,
    ].join(" · ");
  }, [draft, unknown, roofName]);

  const selectedTeamCount = useMemo(
    () => Object.values(draft.team).reduce((sum, count) => sum + count, 0) + draft.customTeam.length,
    [draft.team, draft.customTeam]
  );

  function setTeamCount(roleId: string, count: number) {
    setDraft((current) => {
      const team = { ...current.team };
      if (count <= 0) delete team[roleId];
      else team[roleId] = Math.min(20, count);
      return { ...current, artist: Object.keys(team)[0] || "unknown", team };
    });
    setUnknown((current) => ({ ...current, artist: false }));
  }

  function addPreset(roles: Record<string, number>) {
    setDraft((current) => {
      const team = { ...current.team };
      Object.entries(roles).forEach(([roleId, count]) => {
        team[roleId] = Math.max(team[roleId] || 0, count);
      });
      return { ...current, artist: Object.keys(team)[0] || "unknown", team };
    });
    setUnknown((current) => ({ ...current, artist: false }));
  }

  function addCustomRole() {
    const value = customRole.trim();
    if (!value || draft.customTeam.some((item) => item.toLowerCase() === value.toLowerCase())) return;
    setDraft((current) => ({ ...current, customTeam: [...current.customTeam, value] }));
    setUnknown((current) => ({ ...current, artist: false }));
    setCustomRole("");
  }

  function set<K extends keyof Draft>(key: K, value: Draft[K]) {
    setDraft((d) => ({ ...d, [key]: value }));
  }

  async function submit() {
    if (!getToken()) {
      router.push(loginHref("/events/new"));
      return;
    }
    setSaving(true);
    try {
      const me = await api<{ organizations: { id: string; kind: string }[] }>("/me");
      const org = me.organizations.find((o) => o.kind === "customer") || me.organizations[0];
      if (!org) throw new Error("Сначала войдите как заказчик");
      await api("/events", {
        method: "POST",
        body: JSON.stringify({
          organization_id: org.id,
          title: draft.what.trim() || "Событие",
          city: draft.city || "Москва",
          event_date: draft.date
            ? new Date(draft.date.includes("+") || draft.date.endsWith("Z") ? draft.date : `${draft.date}:00+03:00`).toISOString()
            : new Date().toISOString(),
          guest_count: Number(draft.guests || 50),
          budget_rub: draft.budget ? Number(draft.budget) : null,
          notes: [
            unknown.artist
              ? "состав:требуется помощь оператора"
              : `состав:${[
                  ...TEAM_ROLES.filter((role) => (draft.team[role.id] || 0) > 0).map((role) => `${role.id}x${draft.team[role.id]}`),
                  ...draft.customTeam.map((role) => `custom:${role}`),
                ].join(",")}`,
            unknown.venue
              ? "площадка:пока не знаю"
              : roofName
                ? `площадка:смотрим:${roofName}`
                : `площадка:${draft.venue}`,
            unknown.tech ? "техника:пока не знаю" : `техника:${draft.tech}`,
            unknown.budget ? "бюджет:пока не знаю" : "",
          ]
            .filter(Boolean)
            .join("; "),
        }),
      });
      router.push("/cabinet");
      localStorage.removeItem(DRAFT_KEY);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Не удалось сохранить");
    } finally {
      setSaving(false);
    }
  }

  const s = STEPS[step];
  const saveLabel = !online || saveStatus === "offline" ? "Без сети · сохранено на устройстве" : saveStatus === "saving" ? "Сохраняем…" : "Сохранено автоматически";

  return (
    <main>
      <div className="page-heading-row">
        <div>
          <p className="kicker">Event Studio · 8 шагов</p>
          <h1>Новая заявка</h1>
        </div>
        <span className={`save-indicator ${saveStatus}`} role="status">{saveLabel}</span>
      </div>
      <p className="timeline">Здесь формируется черновик события. Итоговая цена на этом экране не рассчитывается.</p>
      <div className="steps" role="tablist" aria-label="Шаги заявки">
        {STEPS.map((item, i) => (
          <button
            key={item.id}
            type="button"
            className={i === step ? "active" : ""}
            onClick={() => setStep(i)}
            aria-current={i === step ? "step" : undefined}
          >
            {i + 1}
          </button>
        ))}
      </div>
      <p className="timeline">
        Шаг {step + 1} из {STEPS.length}
      </p>
      <button
        type="button"
        className="preview-toggle secondary"
        aria-expanded={previewOpen}
        onClick={() => setPreviewOpen((value) => !value)}
      >
        <span>Превью события</span>
        <span>{previewOpen ? "Скрыть" : "Показать"}</span>
      </button>
      {previewOpen ? (
        <aside className="card tint mobile-preview">
          <h2>Превью события</h2>
          <p>{preview}</p>
          <p className="timeline">Черновик сохраняется автоматически. Итоговые условия поступят с сервера.</p>
        </aside>
      ) : null}
      <div className="wizard">
        <section className="card">
          <h2>{s.q}</h2>
          <p className="timeline">{s.hint}</p>
          {s.id === "what" && (
            <>
              <div className="choice-grid">
                {["Свадьба", "Корпоратив", "День рождения", "Клубная ночь"].map((opt) => (
                  <button
                    key={opt}
                    type="button"
                    className={`choice ${draft.what === opt ? "on" : ""}`}
                    onClick={() => set("what", opt)}
                  >
                    {opt}
                  </button>
                ))}
              </div>
              <label>
                Или своими словами
                <input
                  value={["Свадьба", "Корпоратив", "День рождения", "Клубная ночь"].includes(draft.what) ? "" : draft.what}
                  placeholder="Например, выпускной или презентация"
                  onChange={(e) => set("what", e.target.value)}
                />
              </label>
            </>
          )}
          {s.id === "when" && (
            <>
              <CityField value={draft.city} onChange={(v) => set("city", v)} />
              <label>
                Дата и время
                <input
                  type="datetime-local"
                  min={`${moscowToday()}T00:00`}
                  value={draft.date}
                  onChange={(e) => set("date", e.target.value)}
                />
              </label>
              <p className="timeline">Время указывается по Москве. Пилотный каталог сейчас работает по Москве.</p>
            </>
          )}
          {s.id === "guests" && (
            <>
              <input
                type="number"
                min={1}
                max={5000}
                value={draft.guests}
                onChange={(e) => set("guests", e.target.value)}
              />
              <p className="timeline">Ориентир залу. На цену в этом окне не влияет.</p>
            </>
          )}
          {s.id === "artist" && (
            <div className="team-builder">
              <div className="team-builder-head">
                <div>
                  <strong>Команда события</strong>
                  <p className="timeline">Можно выбрать сразу несколько ролей и указать количество.</p>
                </div>
                <span className={`chip ${selectedTeamCount ? "ok" : "wait"}`}>
                  {selectedTeamCount ? `Выбрано: ${selectedTeamCount}` : "Состав пуст"}
                </span>
              </div>

              <div className="team-presets" aria-label="Готовые составы">
                {TEAM_PRESETS.map((preset) => (
                  <button key={preset.id} type="button" className="team-preset" onClick={() => addPreset(preset.roles)}>
                    <strong>{preset.title}</strong>
                    <span>{preset.description}</span>
                    <small>Добавить набор →</small>
                  </button>
                ))}
              </div>

              <div className="team-role-grid">
                {TEAM_ROLES.map((role) => {
                  const count = draft.team[role.id] || 0;
                  return (
                    <article className={`team-role-card ${count ? "on" : ""}`} key={role.id}>
                      <button
                        type="button"
                        className="team-role-main"
                        aria-pressed={count > 0}
                        onClick={() => setTeamCount(role.id, count ? 0 : 1)}
                      >
                        <span className="team-role-mark" aria-hidden>{role.mark}</span>
                        <span className="team-role-copy">
                          <strong>{role.label}</strong>
                          <small>{role.description}</small>
                        </span>
                        <span className="team-role-state" aria-hidden>{count ? "✓" : "+"}</span>
                      </button>
                      {count ? (
                        <div className="team-quantity" aria-label={`Количество: ${role.label}`}>
                          <button type="button" className="secondary" aria-label={`Уменьшить количество: ${role.label}`} onClick={() => setTeamCount(role.id, count - 1)}>−</button>
                          <span><strong>{count}</strong><small>чел.</small></span>
                          <button type="button" className="secondary" aria-label={`Увеличить количество: ${role.label}`} onClick={() => setTeamCount(role.id, count + 1)}>+</button>
                        </div>
                      ) : null}
                    </article>
                  );
                })}
              </div>

              <form className="custom-role" onSubmit={(event) => { event.preventDefault(); addCustomRole(); }}>
                <label>
                  Другая роль
                  <input value={customRole} maxLength={60} onChange={(event) => setCustomRole(event.target.value)} placeholder="Например, иллюзионист" />
                </label>
                <button type="submit" className="secondary" disabled={!customRole.trim()}>Добавить</button>
              </form>

              {draft.customTeam.length ? (
                <div className="selected-team" aria-label="Добавленные роли">
                  {draft.customTeam.map((role) => (
                    <button key={role} type="button" className="selected-team-chip" onClick={() => setDraft((current) => ({ ...current, customTeam: current.customTeam.filter((item) => item !== role) }))}>
                      {role} <span aria-hidden>×</span>
                    </button>
                  ))}
                </div>
              ) : null}

              {selectedTeamCount ? (
                <button type="button" className="linkish team-clear" onClick={() => setDraft((current) => ({ ...current, artist: "unknown", team: {}, customTeam: [] }))}>
                  Очистить состав
                </button>
              ) : null}
            </div>
          )}
          {s.id === "venue" && (
            <div className="choice-grid">
              {[
                ["own", "Своя площадка"],
                ["need", "Нужна площадка"],
                ["unknown", "Пока не знаю"],
              ].map(([val, label]) => (
                <button
                  key={val}
                  type="button"
                  className={`choice ${(unknown.venue ? "unknown" : draft.venue) === val ? "on" : ""}`}
                  onClick={() => {
                    set("venue", val);
                    setUnknown((u) => ({ ...u, venue: val === "unknown" }));
                    if (val !== "need") setRoofName("");
                  }}
                >
                  {label}
                </button>
              ))}
            </div>
          )}
          {s.id === "tech" && (
            <div className="choice-grid">
              {[
                ["have", "Техника на площадке"],
                ["need", "Нужен подбор"],
                ["unknown", "Пока не знаю"],
              ].map(([val, label]) => (
                <button
                  key={val}
                  type="button"
                  className={`choice ${(unknown.tech ? "unknown" : draft.tech) === val ? "on" : ""}`}
                  onClick={() => {
                    set("tech", val);
                    setUnknown((u) => ({ ...u, tech: val === "unknown" }));
                  }}
                >
                  {label}
                </button>
              ))}
            </div>
          )}
          {s.id === "budget" && (
            <input
              type="number"
              placeholder="ориентир, ₽"
              value={unknown.budget ? "" : draft.budget}
              disabled={unknown.budget}
              onChange={(e) => set("budget", e.target.value)}
            />
          )}
          {s.id === "check" && (
            <p>После отправки заявка появится в кабинете. Серверное предложение с quote_id будет показано в Deal Room.</p>
          )}
          {s.unknown ? (
            <label className="unknown">
              <input
                type="checkbox"
                checked={Boolean(unknown[s.id])}
                onChange={(e) => {
                  const on = e.target.checked;
                  setUnknown((u) => ({ ...u, [s.id]: on }));
                  if (on && (s.id === "artist" || s.id === "venue" || s.id === "tech")) {
                    if (s.id === "artist") {
                      setDraft((current) => ({ ...current, artist: "unknown", team: {}, customTeam: [] }));
                    } else {
                      set(s.id, "unknown");
                    }
                  }
                }}
              />
              {s.id === "artist" ? "Нужна помощь с составом" : "Пока не знаю"}
            </label>
          ) : null}
          {error ? <div className="validation-summary" role="alert"><strong>Проверьте этот шаг</strong><p>{error}</p></div> : null}
          <p className="wizard-actions">
            <button type="button" className="secondary" disabled={step === 0} onClick={() => setStep(step - 1)}>
              Назад
            </button>
            {step < STEPS.length - 1 ? (
              <button
                type="button"
                onClick={() => {
                  if (s.id === "what" && !draft.what.trim()) {
                    setError("Укажите формат события.");
                    return;
                  }
                  if (s.id === "when" && !draft.date) {
                    setError("Укажите дату и время события.");
                    return;
                  }
                  if (s.id === "when" && draft.date.slice(0, 10) < moscowToday()) {
                    setError("Выберите текущую или будущую дату.");
                    return;
                  }
                  if (s.id === "guests" && (!Number(draft.guests) || Number(draft.guests) < 1)) {
                    setError("Укажите количество гостей больше нуля.");
                    return;
                  }
                  if (s.id === "artist" && selectedTeamCount === 0 && !unknown.artist) {
                    setError("Добавьте хотя бы одну роль или выберите помощь с составом.");
                    return;
                  }
                  setError("");
                  setStep(step + 1);
                }}
              >
                Дальше
              </button>
            ) : (
              <button type="button" disabled={saving} onClick={() => void submit()}>
                {saving ? "Сохраняем…" : "Сохранить и в сделки"}
              </button>
            )}
          </p>
        </section>
        <aside className="card tint desktop-preview">
          <h2>Превью события</h2>
          <p>{preview}</p>
          <p className="timeline">Черновик сохраняется автоматически. Итоговые условия поступят с сервера.</p>
          <p>
            <span className="chip wait">Срочный поиск пока недоступен</span>
          </p>
        </aside>
      </div>
    </main>
  );
}
