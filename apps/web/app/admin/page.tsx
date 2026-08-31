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
type Metric = { count: number; unique_entities: number; by_event?: Record<string, number> };
type PaymentMetric = Metric & { by_action: Record<string, number> };
type FunnelStep = { step: string; count: number; conversion_from_prev_pct: number | null };
type Dashboards = {
  funnel: { steps: FunnelStep[] };
  liquidity: {
    search_to_deal_pct: number | null;
    offer_response_pct: number | null;
    searches: number;
    deal_opens: number;
    requests: number;
    offers: number;
  };
  leakage: {
    studio_abandoned: number;
    unanswered_requests: number;
    holds_expired: number;
    holds_without_contract: number;
  };
};
type PeriodMetrics = Record<string, Metric | PaymentMetric | Dashboards> & { dashboards?: Dashboards };
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
  "client.event": "Клиентские события",
  payment: "Платежи",
};

const FUNNEL_STEP_LABELS: Record<string, string> = {
  "event.studio.started": "Studio: старт",
  "event.studio.completed": "Studio: завершение",
  "requirement.created": "Позиции состава",
  "request.created": "Заявки",
  "offer.created": "Офферы",
  "hold.created": "Hold",
  "contract.signed": "Договор",
  "payment.webhook": "Оплата",
};

export default function AdminPage() {
  const [error, setError] = useState("");
  const [queue, setQueue] = useState<Queue | null>(null);
  const [audit, setAudit] = useState<Audit["items"]>([]);
  const [metrics, setMetrics] = useState<Metrics | null>(null);
  const [busyKey, setBusyKey] = useState<string | null>(null);
  const [totpEnabled, setTotpEnabled] = useState(false);
  const [totpSecret, setTotpSecret] = useState("");
  const [totpBusy, setTotpBusy] = useState(false);

  async function load() {
    if (!getToken()) {
      setError("Нужен вход оператора");
      return;
    }
    try {
      const [me, q, a, m] = await Promise.all([
        api<{ totp_enabled?: boolean }>("/me"),
        api<Queue>("/admin/verifications"),
        api<Audit>("/admin/audit"),
        api<Metrics>("/admin/metrics"),
      ]);
      setTotpEnabled(Boolean(me.totp_enabled));
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

  async function enableTotp(e: React.FormEvent) {
    e.preventDefault();
    const secret = totpSecret.trim();
    if (secret.length < 6) return;
    setTotpBusy(true);
    try {
      await api("/admin/totp/enable", { method: "POST", body: JSON.stringify({ secret }) });
      setTotpEnabled(true);
      setTotpSecret("");
      setError("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Не удалось включить 2FA");
    } finally {
      setTotpBusy(false);
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
        <article className="card tint">
          <h2>Второй фактор</h2>
          {totpEnabled ? (
            <p className="timeline">TOTP включён. Для возвратов укажите код в запросе.</p>
          ) : (
            <form onSubmit={enableTotp} style={{ display: "grid", gap: 8, maxWidth: 320 }}>
              <p className="timeline">Пилот: задайте 6+ символов как код второго фактора.</p>
              <label>
                Код TOTP
                <input value={totpSecret} onChange={(e) => setTotpSecret(e.target.value)} minLength={6} required />
              </label>
              <button type="submit" disabled={totpBusy}>
                {totpBusy ? "Сохраняем…" : "Включить 2FA"}
              </button>
            </form>
          )}
        </article>
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
                          {"by_event" in row && row.by_event
                            ? ` · ${Object.entries(row.by_event)
                                .map(([ev, n]) => `${ev}:${n}`)
                                .join(", ")}`
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
        {metrics?.periods["7"]?.dashboards ? (
          <article className="card tint">
            <h2>Дашборды пилота</h2>
            <p className="timeline">Воронка, ликвидность и утечки за 7 дней.</p>
            {(["funnel", "liquidity", "leakage"] as const).map((kind) => {
              const dash = metrics.periods["7"].dashboards!;
              if (kind === "funnel") {
                return (
                  <div key={kind}>
                    <h3>Воронка</h3>
                    <ul>
                      {dash.funnel.steps.map((step) => (
                        <li key={step.step}>
                          {FUNNEL_STEP_LABELS[step.step] || step.step}: {step.count}
                          {step.conversion_from_prev_pct != null ? ` · ${step.conversion_from_prev_pct}%` : ""}
                        </li>
                      ))}
                    </ul>
                  </div>
                );
              }
              if (kind === "liquidity") {
                const liq = dash.liquidity;
                return (
                  <div key={kind}>
                    <h3>Ликвидность</h3>
                    <ul>
                      <li>
                        Поиск → Deal Room: {liq.search_to_deal_pct != null ? `${liq.search_to_deal_pct}%` : "—"} (
                        {liq.deal_opens}/{liq.searches})
                      </li>
                      <li>
                        Заявка → оффер: {liq.offer_response_pct != null ? `${liq.offer_response_pct}%` : "—"} (
                        {liq.offers}/{liq.requests})
                      </li>
                    </ul>
                  </div>
                );
              }
              const leak = dash.leakage;
              return (
                <div key={kind}>
                  <h3>Утечки</h3>
                  <ul>
                    <li>Studio брошено: {leak.studio_abandoned}</li>
                    <li>Заявки без оффера: {leak.unanswered_requests}</li>
                    <li>Hold истёк: {leak.holds_expired}</li>
                    <li>Hold без договора: {leak.holds_without_contract}</li>
                  </ul>
                </div>
              );
            })}
          </article>
        ) : null}
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
