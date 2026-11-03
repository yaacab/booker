"use client";

import { useCallback, useEffect, useState } from "react";
import { api } from "@/lib/api";
import { formatWhen } from "@/lib/format";

type SessionRow = {
  id: string;
  created_at?: string | null;
  expires_at?: string | null;
  last_seen_at?: string | null;
  user_agent?: string | null;
  client_ip?: string | null;
  current: boolean;
  admin_2fa_verified?: boolean;
};

function agentLabel(ua?: string | null): string {
  if (!ua) return "клиент неизвестен";
  if (/Mobile|Android|iPhone/i.test(ua)) return "мобильный браузер";
  if (/Edg\//i.test(ua)) return "Edge";
  if (/Chrome\//i.test(ua)) return "Chrome";
  if (/Firefox\//i.test(ua)) return "Firefox";
  if (/Safari\//i.test(ua)) return "Safari";
  return "браузер";
}

export function ActiveSessions() {
  const [items, setItems] = useState<SessionRow[]>([]);
  const [error, setError] = useState("");
  const [busy, setBusy] = useState(false);

  const reload = useCallback(() => {
    api<{ items: SessionRow[] }>("/me/sessions")
      .then((payload) => {
        setItems(Array.isArray(payload.items) ? payload.items : []);
        setError("");
      })
      .catch((err: Error) => setError(err.message || "Не удалось загрузить сеансы"));
  }, []);

  useEffect(() => {
    reload();
  }, [reload]);

  async function revokeOthers() {
    setBusy(true);
    setError("");
    try {
      await api("/me/sessions/revoke-others", { method: "POST", body: "{}" });
      reload();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Не удалось завершить сеансы");
    } finally {
      setBusy(false);
    }
  }

  async function revokeOne(id: string) {
    setBusy(true);
    setError("");
    try {
      await api(`/me/sessions/${encodeURIComponent(id)}`, { method: "DELETE" });
      reload();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Не удалось завершить сеанс");
    } finally {
      setBusy(false);
    }
  }

  const others = items.filter((row) => !row.current).length;

  return (
    <section className="card" data-testid="active-sessions">
      <h2>Активные сеансы</h2>
      <p className="timeline">Список входов в аккаунт. Можно завершить чужие устройства.</p>
      {error ? <p className="timeline">{error}</p> : null}
      {!items.length && !error ? <p className="timeline">Загружаем…</p> : null}
      {items.length ? (
        <ul className="timeline">
          {items.map((row) => (
            <li key={row.id}>
              {row.current ? <strong>Этот сеанс</strong> : "Другой сеанс"}
              {` · ${agentLabel(row.user_agent)}`}
              {row.client_ip ? ` · ${row.client_ip}` : ""}
              {row.last_seen_at ? ` · активность ${formatWhen(row.last_seen_at)}` : ""}
              {row.created_at ? ` · с ${formatWhen(row.created_at)}` : ""}
              {!row.current ? (
                <>
                  {" "}
                  <button
                    type="button"
                    className="secondary"
                    disabled={busy}
                    onClick={() => void revokeOne(row.id)}
                  >
                    Завершить
                  </button>
                </>
              ) : null}
            </li>
          ))}
        </ul>
      ) : null}
      {others > 0 ? (
        <p>
          <button type="button" disabled={busy} onClick={() => void revokeOthers()}>
            {busy ? "Завершаем…" : "Завершить все остальные"}
          </button>
        </p>
      ) : null}
    </section>
  );
}
