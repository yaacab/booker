"use client";

import Link from "next/link";
import { FormEvent, useEffect, useState } from "react";
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
      <main>
        <p className="kicker">Букер</p>
        <h1>Сохранённые поиски</h1>
        <div className="grid">
          <div className="skeleton" />
        </div>
      </main>
    );
  }

  if (!getToken()) {
    return (
      <main>
        <p className="kicker">Букер</p>
        <h1>Сохранённые поиски</h1>
        <p>{error}</p>
        <p>
          <Link className="btn" href={loginHref("/cabinet/customer/saved-searches")}>
            Войти
          </Link>
        </p>
      </main>
    );
  }

  return (
    <main>
      <p className="kicker">Кабинет заказчика</p>
      <h1>Сохранённые поиски</h1>
      <p className="timeline">
        Параметры каталога для быстрого возврата. Уведомления — только по явному согласию.
      </p>
      <p style={{ display: "flex", gap: 8, flexWrap: "wrap", marginTop: 12 }}>
        <Link className="btn secondary" href="/cabinet/customer">
          К кабинету
        </Link>
        <Link className="btn" href="/search">
          Каталог
        </Link>
      </p>

      <article className="card" style={{ marginTop: 20 }}>
        <h2>Новый поиск</h2>
        <form onSubmit={onSubmit} className="grid" style={{ gap: 12 }}>
          <label>
            Название
            <input
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
          <label style={{ display: "flex", gap: 8, alignItems: "center" }}>
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
            Уведомлять о новых результатах
          </label>
          {form.notify_consent ? (
            <label style={{ display: "flex", gap: 8, alignItems: "center" }}>
              <input
                type="checkbox"
                checked={form.consent}
                onChange={(e) => setForm((f) => ({ ...f, consent: e.target.checked }))}
              />
              Я согласен(на) получать уведомления по этому поиску
            </label>
          ) : null}
          <p>
            <button className="btn" type="submit" disabled={saving}>
              {saving ? "Сохраняем…" : "Сохранить поиск"}
            </button>
          </p>
        </form>
      </article>

      {error ? <p style={{ color: "var(--danger)", marginTop: 16 }}>{error}</p> : null}

      {!error && items.length === 0 ? (
        <article className="card empty" style={{ marginTop: 20 }}>
          <h2>Пока нет сохранённых поисков</h2>
          <p>Сохраните параметры каталога — вернуться к ним можно в один клик.</p>
        </article>
      ) : null}

      {items.length > 0 ? (
        <div className="grid" style={{ marginTop: 20 }}>
          {items.map((item) => (
            <article className="card" key={item.id}>
              <div className="card-head">
                <strong>{item.name}</strong>
              </div>
              <p className="timeline">
                {[
                  item.query_params.city,
                  item.query_params.format && `формат ${item.query_params.format}`,
                  item.query_params.guests && `от ${item.query_params.guests} гостей`,
                  item.query_params.budget_max &&
                    `до ${item.query_params.budget_max.toLocaleString("ru-RU")} ₽`,
                  item.query_params.kind === "artist"
                    ? "артисты"
                    : item.query_params.kind === "venue"
                      ? "площадки"
                      : null,
                ]
                  .filter(Boolean)
                  .join(" · ") || "Без фильтров"}
              </p>
              <p className="timeline">
                Уведомления: {item.notify_consent ? "включены" : "выключены"}
              </p>
              <p style={{ display: "flex", gap: 8, flexWrap: "wrap", marginTop: 8 }}>
                <Link className="btn" href={item.search_path}>
                  Открыть в каталоге
                </Link>
                <button
                  className="btn secondary"
                  type="button"
                  onClick={() => toggleConsent(item, !item.notify_consent)}
                >
                  {item.notify_consent ? "Выключить уведомления" : "Включить уведомления"}
                </button>
                <button className="btn secondary" type="button" onClick={() => remove(item.id)}>
                  Удалить
                </button>
              </p>
            </article>
          ))}
        </div>
      ) : null}
    </main>
  );
}
