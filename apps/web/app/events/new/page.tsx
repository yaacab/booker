"use client";

import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { api, getToken } from "@/lib/api";
import { categoryLabel } from "@/lib/copy";
import { CityField } from "@/components/CityField";
import { moscowToday } from "@/lib/format";
import { loginHref } from "@/lib/next";

const STEPS = [
  { id: "what", q: "Что за вечер?", hint: "Формат, не смета. Смету придумает сервер, если доживём.", unknown: false },
  { id: "when", q: "Когда и в каком городе?", hint: "Без даты покажем красивых, но занятых. Скучно.", unknown: false },
  { id: "guests", q: "Сколько человек влезает?", hint: "Нужно залу и райдеру. На цену в этом окне не влияет — честно.", unknown: false },
  { id: "artist", q: "Кто на сцене?", hint: "Не знаете жанр — так и скажите. Это не экзамен.", unknown: true },
  { id: "venue", q: "Крыша уже есть?", hint: "Можно оставить дыру. Залать потом.", unknown: true },
  { id: "tech", q: "Что с колонками?", hint: "Черновик. Договором это станет позже, если вообще.", unknown: true },
  { id: "budget", q: "Потолок, если есть", hint: "Ориентир человеку. Не счёт и не обещание.", unknown: true },
  { id: "check", q: "Ещё не поздно сбежать", hint: "Дальше можно звать предложения. Цифра приедет с номером.", unknown: false },
] as const;

type Draft = {
  what: string;
  city: string;
  date: string;
  guests: string;
  artist: string;
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

  useEffect(() => {
    try {
      const raw = sessionStorage.getItem(DRAFT_KEY);
      if (raw) {
        const saved = JSON.parse(raw) as {
          draft?: Draft;
          unknown?: Record<string, boolean>;
          step?: number;
          roofName?: string;
        };
        if (saved.draft) setDraft({ ...EMPTY, ...saved.draft });
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
    document.querySelector<HTMLButtonElement>(".steps button.active")?.scrollIntoView({
      inline: "center",
      block: "nearest",
      behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth",
    });
  }, [step]);

  useEffect(() => {
    if (!hydrated) return;
    sessionStorage.setItem(DRAFT_KEY, JSON.stringify({ draft, unknown, step, roofName }));
  }, [draft, unknown, step, roofName, hydrated]);

  const preview = useMemo(() => {
    const artist =
      draft.artist === "unknown" || unknown.artist ? "артист не выбран" : categoryLabel(draft.artist) || draft.artist;
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
            unknown.artist ? "артист:пока не знаю" : `артист:${draft.artist}`,
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
      sessionStorage.removeItem(DRAFT_KEY);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Не удалось сохранить");
    } finally {
      setSaving(false);
    }
  }

  const s = STEPS[step];

  return (
    <main>
      <p className="kicker">Восемь шагов. Без 3D-шара и срочности «на вчера».</p>
      <h1>Собрать вечер</h1>
      <p className="timeline">Цена здесь не считается. Можете выдохнуть: калькулятор мы спрятали специально.</p>
      <div className="steps" role="tablist" aria-label="Шаги вечера">
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
                  placeholder="выпускной, презентация, поминки по Excel"
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
              <p className="timeline">Как в Москве. Каталог тоже считает сутки по МСК, не по Гринвичу. Пилот выдачи — Москва.</p>
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
            <div className="choice-grid">
              {[
                ["dj", "DJ"],
                ["host", "Ведущий"],
                ["cover", "Кавер"],
                ["unknown", "Сюрприз"],
              ].map(([val, label]) => (
                <button
                  key={val}
                  type="button"
                  className={`choice ${draft.artist === val ? "on" : ""}`}
                  onClick={() => {
                    set("artist", val);
                    setUnknown((u) => ({ ...u, artist: val === "unknown" }));
                  }}
                >
                  {label}
                </button>
              ))}
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
            <p>Если всё похоже на правду — сохраняем. Цифра с номером приедет в гримёрку, не в этот экран.</p>
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
                    set(s.id, "unknown");
                  }
                }}
              />
              Пока туман
            </label>
          ) : null}
          {error ? <p style={{ color: "var(--danger)" }}>{error}</p> : null}
          <p className="wizard-actions">
            <button type="button" className="secondary" disabled={step === 0} onClick={() => setStep(step - 1)}>
              Назад
            </button>
            {step < STEPS.length - 1 ? (
              <button
                type="button"
                onClick={() => {
                  if (s.id === "what" && !draft.what.trim()) {
                    setError("Хоть свадьба, хоть поминки по Excel — без названия это не вечер.");
                    return;
                  }
                  if (s.id === "when" && !draft.date) {
                    setError("Без даты это экскурсия по красивым, а не бронь.");
                    return;
                  }
                  if (s.id === "when" && draft.date.slice(0, 10) < moscowToday()) {
                    setError("Вчерашнюю дату календарь не воскрешает.");
                    return;
                  }
                  if (s.id === "guests" && (!Number(draft.guests) || Number(draft.guests) < 1)) {
                    setError("Хотя бы один живой, иначе это репетиция без зала.");
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
        <aside className="card tint">
          <h2>Что уже нацарапали</h2>
          <p>{preview}</p>
          <p className="timeline">Черновик. Юридической силы — как у салфетки, пока нет серверного предложения.</p>
          <p>
            <span className="chip wait">«на вчера» — в следующей жизни</span>
          </p>
        </aside>
      </div>
    </main>
  );
}
