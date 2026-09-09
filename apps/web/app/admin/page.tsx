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
type VenueCatalogRow = { id: string; name: string; address: string; source_type: string; partnership_status: string; is_claimed: boolean; moderation_status: string; completeness_score: number; data_freshness_status: string };
type VenueCatalogReport = { total: number; automated: number; unverified: number; verified: number; partners: number; published: number; needs_review: number };

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
  const [externalPaymentId, setExternalPaymentId] = useState("");
  const [externalBusy, setExternalBusy] = useState(false);
  const [externalNotice, setExternalNotice] = useState("");
  const [venueRows, setVenueRows] = useState<VenueCatalogRow[]>([]);
  const [venueReport, setVenueReport] = useState<VenueCatalogReport | null>(null);
  const [catalogBusy, setCatalogBusy] = useState<string | null>(null);
  const [venueComments, setVenueComments] = useState<Record<string, string>>({});

  async function load() {
    if (!getToken()) {
      setError("Нужен вход оператора");
      return;
    }
    try {
      const [me, q, a, m, catalogRows, catalogReport] = await Promise.all([
        api<{ totp_enabled?: boolean }>("/me"),
        api<Queue>("/admin/verifications"),
        api<Audit>("/admin/audit"),
        api<Metrics>("/admin/metrics"),
        api<{ items: VenueCatalogRow[] }>("/admin/venue-catalog/venues?limit=50"),
        api<VenueCatalogReport>("/admin/venue-catalog/report"),
      ]);
      setTotpEnabled(Boolean(me.totp_enabled));
      setQueue(q);
      setAudit(a.items.slice(0, 20));
      setMetrics(m);
      setVenueRows(catalogRows.items);
      setVenueReport(catalogReport);
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

  async function confirmExternalPayment(e: React.FormEvent) {
    e.preventDefault();
    const id = externalPaymentId.trim();
    if (!id) return;
    setExternalBusy(true);
    setExternalNotice("");
    try {
      await api(`/admin/payments/${encodeURIComponent(id)}/confirm-external`, { method: "POST" });
      setExternalNotice("Оплата подтверждена.");
      setExternalPaymentId("");
      setError("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Не удалось подтвердить оплату");
    } finally {
      setExternalBusy(false);
    }
  }

  async function changeVenueStatus(id: string, partnershipStatus: string) {
    setCatalogBusy(id + ":status");
    try {
      await api("/admin/venue-catalog/venues/" + encodeURIComponent(id) + "/status", {
        method: "POST",
        body: JSON.stringify({
          partnership_status: partnershipStatus,
          comment: venueComments[id]?.trim() || "Изменено оператором",
        }),
      });
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Не удалось изменить статус площадки");
    } finally {
      setCatalogBusy(null);
    }
  }

  async function changeVenueModeration(id: string, moderationStatus: string) {
    setCatalogBusy(id + ":moderation");
    try {
      await api("/admin/venue-catalog/venues/" + encodeURIComponent(id) + "/moderation", {
        method: "POST",
        body: JSON.stringify({
          moderation_status: moderationStatus,
          comment: venueComments[id]?.trim() || "Изменено оператором",
        }),
      });
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Не удалось изменить модерацию");
    } finally {
      setCatalogBusy(null);
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
          <h2>External-оплата</h2>
          <form onSubmit={confirmExternalPayment} style={{ display: "grid", gap: 8, maxWidth: 320 }}>
            <label>
              Payment id
              <input
                value={externalPaymentId}
                onChange={(e) => setExternalPaymentId(e.target.value)}
                required
              />
            </label>
            <button type="submit" disabled={externalBusy}>
              {externalBusy ? "Подтверждаем…" : "Подтвердить external-оплату"}
            </button>
            {externalNotice ? <p className="timeline">{externalNotice}</p> : null}
          </form>
        </article>
        <article className="card" style={{ gridColumn: "1 / -1" }}>
          <h2>Каталог площадок</h2>
          {venueReport ? (
            <p className="timeline">
              Всего: {venueReport.total} · опубликовано: {venueReport.published} · на проверке: {venueReport.needs_review} · подтверждено: {venueReport.verified} · партнеры: {venueReport.partners}
            </p>
          ) : null}
          <div style={{ overflowX: "auto" }}>
            <table style={{ width: "100%", borderCollapse: "collapse" }}>
              <thead><tr><th>Площадка</th><th>Источник</th><th>Сотрудничество</th><th>Подтверждена</th><th>Качество</th><th>Комментарий</th><th>Модерация</th></tr></thead>
              <tbody>
                {venueRows.map((row) => (
                  <tr key={row.id}>
                    <td><strong>{row.name}</strong><br /><span className="timeline">{row.address}</span></td>
                    <td>{row.source_type === "automated_import" ? "Автоматический импорт" : row.source_type}</td>
                    <td>
                      <select value={row.partnership_status} disabled={catalogBusy?.startsWith(row.id)} onChange={(e) => void changeVenueStatus(row.id, e.target.value)}>
                        <option value="unverified_listing">Нет договоренности</option>
                        <option value="claimed">Карточка заявлена</option>
                        <option value="verified">Данные подтверждены</option>
                        <option value="partner">Партнер</option>
                      </select>
                    </td>
                    <td>{row.is_claimed ? "Да" : "Нет"}</td>
                    <td>{row.completeness_score}% · {row.data_freshness_status}</td>
                    <td>
                      <input
                        aria-label={"Комментарий к " + row.name}
                        value={venueComments[row.id] ?? ""}
                        onChange={(e) => setVenueComments((current) => ({ ...current, [row.id]: e.target.value }))}
                        placeholder="Например: представитель подтвердил данные"
                      />
                    </td>
                    <td>
                      <button type="button" disabled={catalogBusy?.startsWith(row.id) || row.moderation_status === "published"} onClick={() => void changeVenueModeration(row.id, "published")}>Опубликовать</button>{" "}
                      <button type="button" className="secondary" disabled={catalogBusy?.startsWith(row.id) || row.moderation_status === "needs_review"} onClick={() => void changeVenueModeration(row.id, "needs_review")}>На проверку</button>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </article>

        <article className="card">
          <h2>Верификация</h2>
          {queue ? (
            <>
              {renderTargets("artist", "Артисты", queue.artists ?? [])}
              {renderTargets("venue", "Площадки", queue.venues ?? [])}
            </>
          ) : !error ? (
            <p className="timeline">Загрузка очереди…</p>
          ) : null}
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
                      if (!row || !("count" in row)) return null;
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
