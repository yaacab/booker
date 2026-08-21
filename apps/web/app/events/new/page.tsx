"use client";

import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { api, getToken } from "@/lib/api";
import { categoryLabel } from "@/lib/copy";
import { CityField } from "@/components/CityField";
import { moscowToday } from "@/lib/format";
import { loginHref } from "@/lib/next";

const STEPS = [
  { id: "what", q: "Формат события", hint: "Выберите базовый сценарий — детали можно изменить позже.", unknown: false },
  { id: "when", q: "Дата и город", hint: "По этим данным каталог проверит доступные слоты.", unknown: false },
  { id: "guests", q: "Количество гостей", hint: "Нужно для подбора формата площадки и требований райдера.", unknown: false },
  { id: "artist", q: "Состав", hint: "Отметьте нужные роли. Это ещё не бронь и не цена — только состав события.", unknown: true },
  { id: "venue", q: "Площадка", hint: "Укажите, есть ли площадка или её нужно подобрать.", unknown: true },
  { id: "tech", q: "Технические условия", hint: "Отметьте текущее состояние — точный райдер согласуется в Deal Room.", unknown: true },
  { id: "budget", q: "Бюджет", hint: "Диапазон помогает отфильтровать варианты, но не рассчитывает итоговую цену.", unknown: true },
  { id: "check", q: "Проверка заявки", hint: "Проверьте данные перед отправкой. Итоговая сумма появится только в серверном предложении.", unknown: false },
] as const;

type Draft = {
  what: string;
  city: string;
  date: string;
  guests: string;
  artist: string;
  roles: string[];
  roleQty: Record<string, number>;
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
  roles: ["dj"],
  roleQty: { dj: 1 },
  venue: "unknown",
  tech: "unknown",
  budget: "",
};

function qtyOf(qty: Record<string, number> | undefined, code: string): number {
  const n = Number(qty?.[code]);
  if (!Number.isFinite(n) || n < 1) return 1;
  return Math.min(20, Math.floor(n));
}

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

  useEffect(() => {
    try {
      const raw = localStorage.getItem(DRAFT_KEY);
      if (raw) {
        const saved = JSON.parse(raw) as {
          draft?: Draft;
          unknown?: Record<string, boolean>;
          step?: number;
          roofName?: string;
        };
        if (saved.draft) {
          const roles = saved.draft.roles || EMPTY.roles;
          const roleQty: Record<string, number> = { ...(saved.draft.roleQty || {}) };
          for (const code of roles) roleQty[code] = qtyOf(roleQty, code);
          setDraft({ ...EMPTY, ...saved.draft, roles, roleQty });
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
    const roles = unknown.artist ? [] : (draft.roles.length ? draft.roles : [draft.artist]).filter((c) => c && c !== "unknown");
    const artist = roles.length
      ? roles
          .map((c) => {
            const n = qtyOf(draft.roleQty, c);
            const label = categoryLabel(c) || c;
            return n > 1 ? `${label} ×${n}` : label;
          })
          .join(", ")
      : "состав не выбран";
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
      const me = await api<{ organizations: { id: string; kind: string }[]; active_organization_id?: string }>("/me");
      const org =
        me.organizations.find((o) => o.id === me.active_organization_id && o.kind === "customer") ||
        me.organizations.find((o) => o.kind === "customer") ||
        me.organizations[0];
      if (!org) throw new Error("Сначала войдите как заказчик");
      const roleCodes = unknown.artist
        ? []
        : (draft.roles.length ? draft.roles : [draft.artist]).filter((c) => c && c !== "unknown");
      const requirements: { category_code: string; qty: number }[] = roleCodes.map((code) => ({
        category_code: code,
        qty: qtyOf(draft.roleQty, code),
      }));
      if (!unknown.venue && draft.venue !== "unknown") {
        requirements.push({ category_code: "venue", qty: 1 });
      }
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
          requirements,
          notes: [
            unknown.artist ? "артист:пока не знаю" : `артист:${roleCodes[0] || draft.artist}`,
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
            <>
              <div className="choice-grid">
                {[
                  ["dj", "DJ"],
                  ["host", "Ведущий"],
                  ["cover", "Кавер"],
                  ["photo", "Фотограф"],
                  ["makeup", "Визажист"],
                  ["unknown", "Помочь с выбором"],
                ].map(([val, label]) => (
                  <button
                    key={val}
                    type="button"
                    className={`choice ${
                      val === "unknown"
                        ? unknown.artist || draft.artist === "unknown"
                          ? "on"
                          : ""
                        : draft.roles.includes(val)
                          ? "on"
                          : ""
                    }`}
                    onClick={() => {
                      if (val === "unknown") {
                        setDraft((d) => ({ ...d, artist: "unknown", roles: [], roleQty: {} }));
                        setUnknown((u) => ({ ...u, artist: true }));
                        return;
                      }
                      setUnknown((u) => ({ ...u, artist: false }));
                      setDraft((d) => {
                        const has = d.roles.includes(val);
                        const roles = has ? d.roles.filter((c) => c !== val) : [...d.roles, val];
                        const roleQty = { ...d.roleQty };
                        if (has) delete roleQty[val];
                        else roleQty[val] = qtyOf(roleQty, val);
                        return { ...d, roles, roleQty, artist: roles[0] || "unknown" };
                      });
                    }}
                  >
                    {label}
                  </button>
                ))}
              </div>
              {!unknown.artist && draft.roles.length ? (
                <>
                  {draft.roles.map((code) => (
                    <label key={code}>
                      {categoryLabel(code) || code} · количество
                      <input
                        type="number"
                        min={1}
                        max={20}
                        value={qtyOf(draft.roleQty, code)}
                        onChange={(e) => {
                          const next = qtyOf({ [code]: Number(e.target.value) }, code);
                          setDraft((d) => ({ ...d, roleQty: { ...d.roleQty, [code]: next } }));
                        }}
                      />
                    </label>
                  ))}
                  <p className="timeline">Количество нужно для состава заявки. На цену в этом окне не влияет.</p>
                </>
              ) : null}
            </>
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
                    if (s.id === "artist") setDraft((d) => ({ ...d, artist: "unknown", roles: [], roleQty: {} }));
                    else set(s.id, "unknown");
                  }
                }}
              />
              Пока не знаю
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
