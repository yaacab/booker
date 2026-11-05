"use client";

import Link from "next/link";
import { FormEvent, useEffect, useRef, useState } from "react";
import { api, getToken } from "@/lib/api";
import { loginHref } from "@/lib/next";

type SavedSearchItem = {
  id: string;
  name: string;
  query_params: {
    format?: string;
    city?: string;
    budget_max?: number;
    guests?: number;
    kind?: string;
  };
  search_path: string;
  notify_consent: boolean;
  created_at?: string | null;
};

const emptyForm = {
  name: "",
  city: "Москва",
  format: "",
  budget_max: "",
  guests: "",
  kind: "",
  notify_consent: false,
  consent: false,
};

export default function CustomerSavedSearchesPage() {
  const [ready, setReady] = useState(false);
  const [error, setError] = useState("");
  const [items, setItems] = useState<SavedSearchItem[]>([]);
  const [form, setForm] = useState(emptyForm);
  const [saving, setSaving] = useState(false);
  const createRef = useRef<HTMLDetailsElement>(null);
  const nameRef = useRef<HTMLInputElement>(null);

  const load = () =>
    api<{ items: SavedSearchItem[] }>("/saved-searches")
      .then((res) => {
        setItems(res.items || []);
        setError("");
      })
      .catch((err: Error) => setError(err.message || "Не удалось загрузить сохранённые поиски"));

  useEffect(() => {
    if (!getToken()) {
      setReady(true);
      setError("Войдите, чтобы сохранять поиски.");
      return;
    }
    let cancelled = false;
    load().finally(() => {
      if (!cancelled) setReady(true);
    });
    return () => {
      cancelled = true;
    };
  }, []);

  async function onSubmit(e: FormEvent) {
    e.preventDefault();
    if (!form.name.trim()) {
      setError("Укажите название поиска");
      return;
    }
    if (form.notify_consent && !form.consent) {
      setError("Для уведомлений отметьте явное согласие");
      return;
    }
    setSaving(true);
    setError("");
    try {
      const query_params: Record<string, string | number> = {};
      if (form.city.trim()) query_params.city = form.city.trim();
      if (form.format.trim()) query_params.format = form.format.trim();
      if (form.kind.trim()) query_params.kind = form.kind.trim();
      if (form.budget_max.trim()) query_params.budget_max = Number(form.budget_max);
      if (form.guests.trim()) query_params.guests = Number(form.guests);
      await api<SavedSearchItem>("/saved-searches", {
        method: "POST",
        body: JSON.stringify({
          name: form.name.trim(),
          query_params,
          notify_consent: form.notify_consent,
          consent: form.consent,
        }),
      });
      setForm(emptyForm);
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Не удалось сохранить поиск");
    } finally {
      setSaving(false);
    }
  }

  async function toggleConsent(item: SavedSearchItem, enable: boolean) {
    if (enable && !window.confirm("Включить уведомления о новых подходящих результатах?")) {
      return;
    }
    setError("");
    try {
      await api<SavedSearchItem>(`/saved-searches/${item.id}/notify-consent`, {
        method: "PATCH",
        body: JSON.stringify({
          notify_consent: enable,
          consent: enable,
        }),
      });
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Не удалось обновить согласие");
    }
  }

  async function remove(id: string) {
    if (!window.confirm("Удалить сохранённый поиск?")) return;
    setError("");
    try {
      await api(`/saved-searches/${id}`, { method: "DELETE" });
      setItems((prev) => prev.filter((row) => row.id !== id));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Не удалось удалить");
    }
  }

  if (!ready) {
    return (
      <main className="saved-searches-reference">
        <header className="saved-searches-heading">
          <div><p className="kicker">Кабинет заказчика</p><h1>Сохранённые поиски</h1></div>
        </header>
        <p role="status">Загружаем ваши подборки…</p>
        <div className="saved-searches-loading" aria-hidden="true">
          <div className="skeleton" /><div className="skeleton" /><div className="skeleton" />
        </div>
      </main>
    );
  }

  if (!getToken()) {
    return (
      <main className="saved-searches-reference">
        <header className="saved-searches-heading">
          <div><p className="kicker">Кабинет заказчика</p><h1>Сохранённые поиски</h1></div>
        </header>
        <section className="saved-searches-empty">
          <p>{error}</p>
          <Link className="btn" href={loginHref("/cabinet/customer/saved-searches")}>
            Войти в кабинет →
          </Link>
        </section>
      </main>
    );
  }

  return (
    <main className="saved-searches-reference">
      <header className="saved-searches-heading">
        <div>
          <p className="kicker">Кабинет заказчика</p>
          <h1>Сохранённые поиски</h1>
          <p>Ваши параметры подбора — чтобы быстро вернуться к поиску.</p>
        </div>
        <button
          className="btn saved-searches-new"
          type="button"
          aria-controls="saved-search-create"
          onClick={() => {
            if (createRef.current) createRef.current.open = true;
            nameRef.current?.focus();
          }}
        >
          <span aria-hidden="true">＋</span> Новый поиск
        </button>
      </header>

      {error ? <p className="saved-searches-error" role="alert">{error}</p> : null}

      {items.length > 0 ? (
        <section aria-label="Ваши сохранённые поиски">
          <div className="saved-searches-list-heading">
            <p>Сохранено: <strong>{items.length}</strong></p>
            <Link href="/search">Открыть каталог <span aria-hidden="true">↗</span></Link>
          </div>
          <ul className="saved-searches-list">
            {items.map((item) => {
              const createdAt = item.created_at && Number.isFinite(Date.parse(item.created_at))
                ? new Date(item.created_at).toLocaleDateString("ru-RU", { day: "numeric", month: "long", year: "numeric" })
                : null;
              const description = [
                item.query_params.kind === "artist" ? "Артисты" : item.query_params.kind === "venue" ? "Площадки" : null,
                item.query_params.city,
                item.query_params.format && `формат ${item.query_params.format}`,
                item.query_params.guests && `от ${item.query_params.guests} гостей`,
                item.query_params.budget_max != null && `бюджет до ${item.query_params.budget_max.toLocaleString("ru-RU")} ₽`,
              ].filter(Boolean).join(" · ") || "Без фильтров";
              return (
                <li key={item.id} className="saved-search-row">
                  <Link className="saved-search-result" href={item.search_path} aria-label={`Открыть в каталоге: ${item.name}`} aria-describedby={`saved-search-details-${item.id}`}>
                    <span className={`saved-search-art${item.query_params.kind === "venue" ? " saved-search-art-venue" : ""}`} aria-hidden="true">
                      <svg width="30" height="30" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.4" strokeLinecap="round" strokeLinejoin="round">
                        {item.query_params.kind === "venue" ? <><path d="M3 21V9l9-6 9 6v12M2 21h20M9 21v-6h6v6" /><path d="M7 10h1m8 0h1M7 13h1m8 0h1" /></> : item.query_params.kind === "artist" ? <><rect x="9" y="2" width="6" height="13" rx="3" /><path d="M5 10v2a7 7 0 0 0 14 0v-2m-7 9v3m-4 0h8" /></> : <><circle cx="10.5" cy="10.5" r="6.5" /><path d="m15.5 15.5 5 5" /></>}
                      </svg>
                    </span>
                    <span className="saved-search-copy">
                      <strong>{item.name}</strong>
                      <span className="saved-search-description" id={`saved-search-details-${item.id}`}>{description}</span>
                      {createdAt ? <span className="saved-search-created">Сохранён {createdAt}</span> : null}
                    </span>
                    <span className="saved-search-arrow" aria-hidden="true">↗</span>
                  </Link>
                  <div className="saved-search-controls">
                    <button
                      className="secondary saved-search-notify"
                      type="button"
                      role="switch"
                      aria-checked={item.notify_consent}
                      aria-label={`Уведомления для поиска «${item.name}»`}
                      onClick={() => toggleConsent(item, !item.notify_consent)}
                    >
                      <span className="saved-search-switch" aria-hidden="true"><span /></span>
                      <span>Уведомления<span className="saved-search-notify-state">{item.notify_consent ? "Включены" : "Выключены"}</span></span>
                    </button>
                    <button
                      className="secondary saved-search-remove"
                      type="button"
                      aria-label={`Удалить поиск «${item.name}»`}
                      onClick={() => remove(item.id)}
                    >
                      Удалить
                    </button>
                  </div>
                </li>
              );
            })}
          </ul>
        </section>
      ) : !error ? (
        <section className="saved-searches-empty">
          <span className="saved-searches-empty-icon" aria-hidden="true">
            <svg width="32" height="32" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round"><circle cx="10" cy="10" r="6" /><path d="m15 15 6 6M7 10h6m-3-3v6" /></svg>
          </span>
          <h2>Пока нет сохранённых поисков</h2>
          <p>Сохраните город, формат и другие параметры подбора. Они появятся здесь, и вы сможете вернуться к ним в один клик.</p>
          <Link href="/search">Посмотреть каталог <span aria-hidden="true">→</span></Link>
        </section>
      ) : null}

      <details className="saved-search-create" id="saved-search-create" ref={createRef}>
        <summary><span><strong>Новый сохранённый поиск</strong><span>Название и параметры вашей подборки</span></span><span className="saved-search-create-plus" aria-hidden="true">＋</span></summary>
        <form onSubmit={onSubmit} className="saved-search-form">
          <label>
            Название
            <input
              ref={nameRef}
              value={form.name}
              onChange={(e) => setForm((f) => ({ ...f, name: e.target.value }))}
              placeholder="DJ на корпоратив"
              required
            />
          </label>
          <label>
            Город
            <input
              value={form.city}
              onChange={(e) => setForm((f) => ({ ...f, city: e.target.value }))}
            />
          </label>
          <label>
            Формат
            <input
              value={form.format}
              onChange={(e) => setForm((f) => ({ ...f, format: e.target.value }))}
              placeholder="dj, live, …"
            />
          </label>
          <label>
            Бюджет до, ₽
            <input
              type="number"
              min={0}
              value={form.budget_max}
              onChange={(e) => setForm((f) => ({ ...f, budget_max: e.target.value }))}
            />
          </label>
          <label>
            Гостей от
            <input
              type="number"
              min={1}
              value={form.guests}
              onChange={(e) => setForm((f) => ({ ...f, guests: e.target.value }))}
            />
          </label>
          <label>
            Тип
            <select
              value={form.kind}
              onChange={(e) => setForm((f) => ({ ...f, kind: e.target.value }))}
            >
              <option value="">Любой</option>
              <option value="artist">Артист</option>
              <option value="venue">Площадка</option>
            </select>
          </label>
          <fieldset className="saved-search-consent">
            <legend>Уведомления по этому поиску</legend>
            <label className="saved-search-check">
              <input
                type="checkbox"
                checked={form.notify_consent}
                onChange={(e) =>
                  setForm((f) => ({
                    ...f,
                    notify_consent: e.target.checked,
                    consent: e.target.checked ? f.consent : false,
                  }))
                }
              />
              <span>Уведомлять о новых результатах</span>
            </label>
            {form.notify_consent ? (
              <label className="saved-search-check">
                <input
                  type="checkbox"
                  checked={form.consent}
                  onChange={(e) => setForm((f) => ({ ...f, consent: e.target.checked }))}
                />
                <span>Я согласен(на) получать уведомления по этому поиску</span>
              </label>
            ) : null}
            <p>Уведомления включаются только с вашего явного согласия. Его можно отозвать в любой момент.</p>
          </fieldset>
          <div className="saved-search-form-actions">
            <button className="btn" type="submit" disabled={saving}>
              {saving ? "Сохраняем…" : "Сохранить поиск"}
            </button>
          </div>
        </form>
      </details>
      <p className="saved-searches-back"><Link href="/cabinet/customer">← К кабинету заказчика</Link></p>
    </main>
  );
}
