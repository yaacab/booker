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
type Metric = { count: number; unique_entities: number };
type PaymentMetric = Metric & { by_action: Record<string, number> };
type PeriodMetrics = Record<string, Metric | PaymentMetric>;
type Metrics = { periods: { "7": PeriodMetrics; "30": PeriodMetrics } };

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

const FUNNEL_LABELS: Record<string, string> = {
  "request.created": "Заявки",
  "offer.created": "Офферы",
  "workspace.switched": "Смены workspace",
  "service.created": "Услуги",
  "hall.created": "Залы",
  payment: "Платежи",
};

export default function AdminPage() {
  const [error, setError] = useState("");
  const [queue, setQueue] = useState<Queue | null>(null);
  const [audit, setAudit] = useState<Audit["items"]>([]);
  const [metrics, setMetrics] = useState<Metrics | null>(null);
  const [busyKey, setBusyKey] = useState<string | null>(null);

  async function load() {
    if (!getToken()) {
      setError("Нужен вход оператора");
      return;
    }
    try {
      const [q, a, m] = await Promise.all([
        api<Queue>("/admin/verifications"),
        api<Audit>("/admin/audit"),
        api<Metrics>("/admin/metrics"),
      ]);
      setQueue(q);
      setAudit(a.items.slice(0, 20));
      setMetrics(m);
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
          <h2>Воронка пилота</h2>
          <p className="timeline">Агрегаты из журнала аудита за 7 и 30 дней.</p>
          {metrics ? (
            <div className="grid">
              {(["7", "30"] as const).map((days) => (
                <div key={days}>
                  <h3>{days} дней</h3>
                  <ul>
                    {Object.entries(FUNNEL_LABELS).map(([key, label]) => {
                      const row = metrics.periods[days][key];
                      if (!row) return null;
                      return (
                        <li key={key}>
                          {label}: {row.count}
                          {"unique_entities" in row && row.unique_entities !== row.count
                            ? ` · уник. ${row.unique_entities}`
                            : ""}
                        </li>
                      );
                    })}
                  </ul>
                </div>
              ))}
            </div>
          ) : (
            <p>Загрузка метрик…</p>
          )}
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
