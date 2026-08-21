"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { api, getToken } from "@/lib/api";
import { formatWhen } from "@/lib/format";
import { loginHref } from "@/lib/next";

type Queue = {
  queue: { id: string; target_type: string; target_id: string }[];
  artists: { id: string; name: string; status: string }[];
};
type Audit = { items: { id: string; action: string; entity_type: string; created_at: string }[] };

const ACTION: Record<string, string> = {
  "slot.created": "слот",
  "request.created": "заявка",
  "offer.created": "оффер",
  "offer.ack": "кивок",
  "offer.version": "новая версия цены",
  "hold.created": "hold",
  "dispute.opened": "спор",
  "verification.decided": "верификация",
};

export default function AdminPage() {
  const [error, setError] = useState("");
  const [queue, setQueue] = useState<Queue | null>(null);
  const [audit, setAudit] = useState<Audit["items"]>([]);
  const [busyId, setBusyId] = useState<string | null>(null);

  async function load() {
    if (!getToken()) {
      setError("Нужен вход оператора");
      return;
    }
    try {
      const [q, a] = await Promise.all([api<Queue>("/admin/verifications"), api<Audit>("/admin/audit")]);
      setQueue(q);
      setAudit(a.items.slice(0, 20));
      setError("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Нет доступа");
    }
  }

  useEffect(() => {
    void load();
  }, []);

  async function decide(artistId: string, approve: boolean) {
    setBusyId(artistId);
    try {
      await api("/admin/verifications", {
        method: "POST",
        body: JSON.stringify({ target_type: "artist", target_id: artistId, approve, notes: "" }),
      });
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Не удалось решить");
    } finally {
      setBusyId(null);
    }
  }

  return (
    <main>
      <p className="kicker">За кулисами</p>
      <h1>Пульт. Нервы прилагаются.</h1>
      <p className="timeline">Споры судит человек. Журнал не стирается. Страховкой не прикидываемся.</p>
      {error ? (
        <p>
          {error}. <Link href={loginHref("/admin")}>Войти</Link>
        </p>
      ) : null}
      <div className="grid">
        <article className="card">
          <h2>Верификация</h2>
          {(queue?.artists ?? []).map((a) => (
            <p key={a.id}>
              {a.name} · {a.status === "pending" ? "ещё знакомимся" : a.status}{" "}
              <button type="button" disabled={busyId === a.id} onClick={() => void decide(a.id, true)}>
                Подтвердить
              </button>{" "}
              <button
                type="button"
                className="secondary"
                disabled={busyId === a.id}
                onClick={() => void decide(a.id, false)}
              >
                Отказать
              </button>
            </p>
          ))}
          {(queue?.artists.length ?? 0) === 0 ? <p>Очередь пуста.</p> : null}
        </article>
        <article className="card">
          <h2>Споры</h2>
          <p>Категория из гримёрки. Вердикт пишет человек, не чат.</p>
        </article>
        <article className="card tint">
          <h2>Риск</h2>
          <p>Прямой перевод вне платформы, просроченный hold, отказ платежа — в журнале.</p>
        </article>
        <article className="card">
          <h2>Поддержка</h2>
          <p>Пилот: живой оператор, цель ответа в рабочее окно — 30 минут на срыв даты.</p>
        </article>
        <article className="card">
          <h2>Аудит</h2>
          <ul>
            {audit.map((row) => (
              <li key={row.id} className="mono">
                {ACTION[row.action] || row.action} · {row.entity_type} · {formatWhen(row.created_at)}
              </li>
            ))}
          </ul>
        </article>
      </div>
    </main>
  );
}
