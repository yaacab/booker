"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { api, getToken } from "@/lib/api";
import { formatWhen } from "@/lib/format";
import { loginHref } from "@/lib/next";
import AdminSupportQueue from "@/components/AdminSupportQueue";
import DataSubjectRequests from "@/components/DataSubjectRequests";
import SupportOperatorManagement from "@/components/SupportOperatorManagement";

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
type DisputeEvidence = { id: string; attachment_id: string; note: string; created_at: string };
type DisputeCase = {
  id: string;
  booking_id: string;
  assigned_to_user_id: string | null;
  category: string;
  notes: string;
  status: "open" | "in_review" | "resolved";
  priority: "urgent" | "high" | string;
  response_due_at: string | null;
  state_version: number;
  decision_kind: string | null;
  decision_note: string;
  created_at: string;
  evidence: DisputeEvidence[];
};
type ExternalEvidence = { evidence_version: number; payment_status: string; reliable_money_fact: boolean; reports: { id: string; status: string; reference: string }[]; timeline: { id: string; report_id: string; kind: string; created_at: string }[] };

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
  "contract.draft_acknowledged": "Техническое подтверждение черновика",
  "payment.webhook": "Оплата",
};

const DISPUTE_CATEGORY_LABELS: Record<string, string> = {
  no_show: "Неявка",
  delay: "Опоздание",
  quality: "Качество услуги",
  payment: "Оплата",
  cancel: "Отмена",
};

const DISPUTE_DECISION_LABELS: Record<string, string> = {
  information_only: "Информация принята",
  service_adjustment_recommended: "Рекомендовать корректировку услуги",
  refund_review_required: "Передать на отдельную проверку возврата",
  rejected: "Отклонить спор",
};

export default function AdminPage() {
  const [error, setError] = useState("");
  const [queue, setQueue] = useState<Queue | null>(null);
  const [audit, setAudit] = useState<Audit["items"]>([]);
  const [metrics, setMetrics] = useState<Metrics | null>(null);
  const [busyKey, setBusyKey] = useState<string | null>(null);
  const [totpEnabled, setTotpEnabled] = useState(false);
  const [isPlatformAdmin, setIsPlatformAdmin] = useState(false);
  const [externalPaymentId, setExternalPaymentId] = useState("");
  const [externalBusy, setExternalBusy] = useState(false);
  const [externalNotice, setExternalNotice] = useState("");
  const [externalEvidence, setExternalEvidence] = useState<ExternalEvidence | null>(null);
  const [externalReportId, setExternalReportId] = useState("");
  const [externalReviewNote, setExternalReviewNote] = useState("");
  const [externalTotp, setExternalTotp] = useState("");
  const [venueRows, setVenueRows] = useState<VenueCatalogRow[]>([]);
  const [venueReport, setVenueReport] = useState<VenueCatalogReport | null>(null);
  const [catalogBusy, setCatalogBusy] = useState<string | null>(null);
  const [venueComments, setVenueComments] = useState<Record<string, string>>({});
  const [operatorId, setOperatorId] = useState("");
  const [disputes, setDisputes] = useState<DisputeCase[]>([]);
  const [disputeTotp, setDisputeTotp] = useState("");
  const [disputeBusy, setDisputeBusy] = useState<string | null>(null);
  const [disputeNotes, setDisputeNotes] = useState<Record<string, string>>({});
  const [disputeDecisions, setDisputeDecisions] = useState<Record<string, string>>({});

  async function load() {
    if (!getToken()) {
      setIsPlatformAdmin(false);
      setError("Нужен вход оператора");
      return;
    }
    try {
      const me = await api<{ id: string; is_platform_admin?: boolean; totp_enabled?: boolean }>("/me");
      setOperatorId(me.id);
      setIsPlatformAdmin(Boolean(me.is_platform_admin));
      setTotpEnabled(Boolean(me.totp_enabled));
      const [q, a, m, catalogRows, catalogReport, disputeQueue] = await Promise.all([
        api<Queue>("/admin/verifications"),
        api<Audit>("/admin/audit"),
        api<Metrics>("/admin/metrics"),
        api<{ items: VenueCatalogRow[] }>("/admin/venue-catalog/venues?limit=50"),
        api<VenueCatalogReport>("/admin/venue-catalog/report"),
        api<{ items: DisputeCase[] }>("/admin/disputes"),
      ]);
      setQueue(q);
      setAudit(a.items.slice(0, 20));
      setMetrics(m);
      setVenueRows(catalogRows.items);
      setVenueReport(catalogReport);
      setDisputes(disputeQueue.items);
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

  async function confirmExternalPayment(e: React.FormEvent) {
    e.preventDefault();
    const id = externalPaymentId.trim();
    if (!id) return;
    setExternalBusy(true);
    setExternalNotice("");
    try {
      await api(`/admin/payments/${encodeURIComponent(id)}/confirm-external?totp=${encodeURIComponent(externalTotp)}`, { method: "POST", body: JSON.stringify({ report_id: externalReportId, review_note: externalReviewNote, recipient_confirmed: true }) });
      setExternalNotice("Сведения сторон проверены. Банковское зачисление не установлено.");
      await loadExternalEvidence(id);
      setError("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Не удалось проверить сведения");
    } finally {
      setExternalBusy(false);
    }
  }

  async function loadExternalEvidence(id = externalPaymentId.trim()) {
    if (!id || !externalTotp.trim()) return;
    try {
      const details = await api<ExternalEvidence>(`/admin/payments/${encodeURIComponent(id)}/external-reports?totp=${encodeURIComponent(externalTotp)}`);
      setExternalEvidence(details);
      setExternalReportId(details.reports[0]?.id ?? "");
      setError("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Не удалось загрузить сведения");
    }
  }

  async function approveExternalCorrection(eventId: string) {
    const id = externalPaymentId.trim();
    if (!id || !externalEvidence) return;
    setExternalBusy(true);
    try {
      await api(`/admin/payments/${encodeURIComponent(id)}/external-corrections/approve?totp=${encodeURIComponent(externalTotp)}`, {
        method: "POST", body: JSON.stringify({ request_event_id: eventId, expected_version: externalEvidence.evidence_version, idempotency_key: crypto.randomUUID() }),
      });
      setExternalNotice("Отметка исправлена. Денежный факт не установлен; выплата заблокирована.");
      await loadExternalEvidence(id);
      setError("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Не удалось исправить отметку");
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

  async function assignDispute(row: DisputeCase) {
    setDisputeBusy(`${row.id}:assign`);
    try {
      await api(`/admin/disputes/${encodeURIComponent(row.id)}/assignment`, {
        method: "PUT",
        body: JSON.stringify({
          assignee_user_id: operatorId,
          state_version: row.state_version,
          totp: disputeTotp.trim() || null,
        }),
      });
      setDisputeTotp("");
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Не удалось назначить спор");
    } finally {
      setDisputeBusy(null);
    }
  }

  async function resolveDispute(row: DisputeCase) {
    const decisionNote = disputeNotes[row.id]?.trim() || "";
    if (decisionNote.length < 3) {
      setError("Добавьте основание решения спора");
      return;
    }
    setDisputeBusy(`${row.id}:resolve`);
    try {
      await api(`/admin/disputes/${encodeURIComponent(row.id)}/resolve`, {
        method: "PUT",
        body: JSON.stringify({
          decision_kind: disputeDecisions[row.id] || "information_only",
          decision_note: decisionNote,
          state_version: row.state_version,
          totp: disputeTotp.trim() || null,
        }),
      });
      setDisputeTotp("");
      setDisputeNotes((current) => ({ ...current, [row.id]: "" }));
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Не удалось завершить спор");
    } finally {
      setDisputeBusy(null);
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
            <p className="timeline">Настройка второго фактора требует подтверждения по почте. <Link href={`${loginHref("/admin")}&enroll=1`}>Перейти к настройке</Link>. Текущий сеанс завершится.</p>
          )}
        </article>
        <article className="card">
          <h2>Сведения о внешнем переводе</h2>
          <p>Отчёт плательщика и ручная проверка не доказывают банковское зачисление.</p>
          <form onSubmit={confirmExternalPayment} style={{ display: "grid", gap: 8, maxWidth: 320 }}>
            <label>
              Payment id
              <input
                value={externalPaymentId}
                onChange={(e) => setExternalPaymentId(e.target.value)}
                required
              />
            </label>
            <label>Код TOTP<input value={externalTotp} onChange={(e) => setExternalTotp(e.target.value)} required minLength={6} /></label>
            <button type="button" className="secondary" onClick={() => void loadExternalEvidence()} disabled={externalBusy}>Загрузить историю</button>
            {externalEvidence ? <>
              <p>Версия сведений: {externalEvidence.evidence_version}. Достоверный денежный факт: не установлен.</p>
              <label>Отчёт<select value={externalReportId} onChange={(e) => setExternalReportId(e.target.value)}>{externalEvidence.reports.map((row) => <option key={row.id} value={row.id}>{row.id} · {row.status}</option>)}</select></label>
              <label>Итог проверки<input value={externalReviewNote} onChange={(e) => setExternalReviewNote(e.target.value)} required minLength={3} maxLength={1000} /></label>
              <ol aria-label="Хронология сведений">{externalEvidence.timeline.map((row) => <li key={row.id}>{row.kind === "payer_reported" ? "Сообщил плательщик" : row.kind === "recipient_acknowledged" ? "Подтвердил получатель" : row.kind === "admin_evidence_reviewed" ? "Проверил оператор" : row.kind === "correction_requested" ? "Запрошено исправление" : row.kind === "correction_approved" ? "Отметка исправлена" : row.kind} · {formatWhen(row.created_at)}{row.kind === "correction_requested" ? <button type="button" disabled={externalBusy} onClick={() => void approveExternalCorrection(row.id)}>Подтвердить исправление другим оператором</button> : null}</li>)}</ol>
            </> : null}
            <button type="submit" disabled={externalBusy}>
              {externalBusy ? "Проверяем…" : "Учесть проверенные сведения сторон"}
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
        <article className="card" style={{ gridColumn: "1 / -1" }}>
          <h2>Споры</h2>
          <p className="timeline">
            Категория и проверенные материалы поступают из Deal Room. Денежное действие оформляется отдельным процессом.
          </p>
          {disputes.some((row) => row.status !== "resolved") ? (
            <label style={{ display: "grid", gap: 6, maxWidth: 280, marginBottom: 16 }}>
              Код TOTP для назначения и решения
              <input
                inputMode="numeric"
                autoComplete="one-time-code"
                value={disputeTotp}
                onChange={(event) => setDisputeTotp(event.target.value)}
              />
            </label>
          ) : null}
          <div style={{ display: "grid", gap: 16 }}>
            {disputes.map((row) => {
              const assignedToMe = row.assigned_to_user_id === operatorId;
              const isBusy = disputeBusy?.startsWith(row.id);
              return (
                <section key={row.id} className="card" aria-label={`Спор ${row.id}`}>
                  <p className="kicker">
                    {row.priority === "urgent" ? "Срочно" : "Высокий приоритет"} · {DISPUTE_CATEGORY_LABELS[row.category] || row.category}
                  </p>
                  <h3>
                    <Link href={`/deals/${row.booking_id}`}>Бронь {row.booking_id}</Link>
                  </h3>
                  <p>{row.notes || "Комментарий не добавлен."}</p>
                  <p className="timeline">
                    Статус: {row.status === "open" ? "новый" : row.status === "in_review" ? "в работе" : "решён"} · срок ответа: {formatWhen(row.response_due_at)} · доказательств: {row.evidence.length}
                  </p>
                  {row.evidence.length > 0 ? (
                    <ul>
                      {row.evidence.map((item) => (
                        <li key={item.id} className="mono">
                          Вложение {item.attachment_id}{item.note ? ` · ${item.note}` : ""}
                        </li>
                      ))}
                    </ul>
                  ) : null}
                  {row.status === "resolved" ? (
                    <p>
                      <strong>{DISPUTE_DECISION_LABELS[row.decision_kind || ""] || row.decision_kind}</strong>
                      {row.decision_note ? ` · ${row.decision_note}` : ""}
                    </p>
                  ) : (
                    <div style={{ display: "grid", gap: 10 }}>
                      {!assignedToMe ? (
                        <button type="button" disabled={isBusy || !operatorId} onClick={() => void assignDispute(row)}>
                          {isBusy ? "Сохраняем…" : row.assigned_to_user_id ? "Переназначить на себя" : "Взять в работу"}
                        </button>
                      ) : (
                        <>
                          <label>
                            Решение
                            <select
                              value={disputeDecisions[row.id] || "information_only"}
                              onChange={(event) => setDisputeDecisions((current) => ({ ...current, [row.id]: event.target.value }))}
                            >
                              {Object.entries(DISPUTE_DECISION_LABELS).map(([value, label]) => (
                                <option key={value} value={value}>{label}</option>
                              ))}
                            </select>
                          </label>
                          <label>
                            Основание решения
                            <textarea
                              rows={3}
                              value={disputeNotes[row.id] || ""}
                              onChange={(event) => setDisputeNotes((current) => ({ ...current, [row.id]: event.target.value }))}
                            />
                          </label>
                          <button type="button" disabled={isBusy} onClick={() => void resolveDispute(row)}>
                            {isBusy ? "Сохраняем…" : "Завершить рассмотрение"}
                          </button>
                        </>
                      )}
                    </div>
                  )}
                </section>
              );
            })}
            {disputes.length === 0 ? <p>Очередь споров пуста.</p> : null}
          </div>
        </article>
        <article className="card tint">
          <h2>Риск</h2>
          <p>Прямой перевод вне платформы, просроченный hold, отказ платежа — в журнале.</p>
        </article>
        {isPlatformAdmin ? (
          <article className="card" style={{ gridColumn: "1 / -1", minWidth: 0 }}>
            <SupportOperatorManagement totpEnabled={totpEnabled} />
          </article>
        ) : null}
        <article className="card" style={{ gridColumn: "1 / -1", minWidth: 0 }}>
          <AdminSupportQueue operatorId={operatorId} />
        </article>
        <article className="card" style={{ gridColumn: "1 / -1", minWidth: 0 }}>
          <DataSubjectRequests mode="admin" />
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
