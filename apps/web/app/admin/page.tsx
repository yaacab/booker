"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { api, getToken } from "@/lib/api";
import { formatWhen } from "@/lib/format";
import { loginHref } from "@/lib/next";

type VerifyTarget = { id: string; name: string; status: string };

type Queue = {
  queue: { id: string; target_type: string; target_id: string }[];
  artists: VerifyTarget[];
  venues?: VerifyTarget[];
};
type Audit = { items: { id: string; action: string; entity_type: string; created_at: string }[] };

const ACTION: Record<string, string> = {
  "slot.created": "слот",
  "request.created": "заявка",
  "requirement.created": "требование",
  "offer.created": "оффер",
  "offer.ack": "кивок",
  "offer.version": "новая версия цены",
  "hold.created": "hold",
  "dispute.opened": "спор",
  "verification.decided": "верификация",
  "workspace.switched": "смена workspace",
  "service.created": "услуга",
  "hall.created": "зал",
};

export default function AdminPage() {
  const [error, setError] = useState("");
  const [queue, setQueue] = useState<Queue | null>(null);
  const [audit, setAudit] = useState<Audit["items"]>([]);
  const [busyKey, setBusyKey] = useState<string | null>(null);

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

  async function decide(targetType: "artist" | "venue", targetId: string, approve: boolean) {
    const key = `${targetType}:${targetId}`;
    setBusyKey(key);
    try {
      await api("/admin/verifications", {
        method: "POST",
        body: JSON.stringify({ target_type: targetType, target_id: targetId, approve, notes: "" }),
      });
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Не удалось решить");
    } finally {
      setBusyKey(null);
    }
  }

  function renderTargets(targetType: "artist" | "venue", title: string, items: VerifyTarget[]) {
    return (
      <>
        <h3>{title}</h3>
        {items.map((item) => {
          const key = `${targetType}:${item.id}`;
          return (
            <p key={item.id}>
              {item.name} · {item.status === "pending" ? "ожидает проверки" : item.status}{" "}
              <button type="button" disabled={busyKey === key} onClick={() => void decide(targetType, item.id, true)}>
                Подтвердить
              </button>{" "}
              <button
                type="button"
                className="secondary"
                disabled={busyKey === key}
                onClick={() => void decide(targetType, item.id, false)}
              >
                Отказать
              </button>
            </p>
          );
        })}
        {items.length === 0 ? <p>Очередь пуста.</p> : null}
      </>
    );
  }

  return (
    <main>
      <p className="kicker">Операторский контур</p>
      <h1>Пульт управления</h1>
      <p className="timeline">Спорные ситуации рассматривает оператор. Действия сохраняются в журнале аудита.</p>
      {error ? (
        <p>
          {error}. <Link href={loginHref("/admin")}>Войти</Link>
        </p>
      ) : null}
      <div className="grid">
        <article className="card">
          <h2>Верификация</h2>
          {renderTargets("artist", "Артисты", queue?.artists ?? [])}
          {renderTargets("venue", "Площадки", queue?.venues ?? [])}
        </article>
        <article className="card">
          <h2>Споры</h2>
          <p>Категория и материалы поступают из Deal Room. Решение принимает оператор.</p>
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
