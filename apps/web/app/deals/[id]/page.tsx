"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { DealRoomSummary } from "@/components/deal-room/DealRoomSummary";
import { HoldCountdown } from "@/components/HoldCountdown";
import { api, trackClientEvent } from "@/lib/api";
import { orgKindToDealRoomAccentKind } from "@/lib/dealRoomAccents";
import { contractDraftAckBody, contractDraftStatus, type ContractDraftEvidence } from "@/lib/contractDraft";
import { formatWhen, money } from "@/lib/format";
import { nextAction, STAGE_ORDER, STATUS_LABEL } from "@/lib/status";

const TABS = [
  { id: "summary", label: "Сводка" },
  { id: "chat", label: "Чат" },
  { id: "terms", label: "Условия" },
  { id: "documents", label: "Документы" },
  { id: "payments", label: "Платежи" },
  { id: "dispute", label: "Спор" },
  { id: "stages", label: "Этапы" },
] as const;

type Room = {
  booking_id: string;
  offer_id: string;
  event_id?: string;
  requirement_id?: string | null;
  status: string;
  role: "customer" | "supplier";
  workspace_kind?: string;
  next_step: string;
  next_action?: { kind: "pay_obligation" | "booking_stage"; obligation_id?: string; label: string };
  event_title?: string;
  participants?: { role: string; name: string; duty: string }[];
  hold?: { status: string; expires_at: string } | null;
  quote: {
    quote_id: string;
    honorarium_rub: number;
    commission_rub: number;
    total_rub: number;
    customer_ack: boolean;
    supplier_ack: boolean;
    source?: string;
  };
  contract: (ContractDraftEvidence & {
    customer_signed: boolean;
    supplier_signed: boolean;
    otp_pending: boolean;
    acknowledgements: {
      side: "customer" | "supplier";
      organization_id: string;
      actor_user_id: string | null;
      actor_role_snapshot: string | null;
      offer_version_id: string | null;
      body_sha256: string | null;
      effect: string;
      created_at: string;
    }[];
  }) | null;
  documents?: { kind: string; id: string; label: string; quote_id?: string; signed: boolean; scan_status?: string; downloadable?: boolean }[];
  payment: { id: string; status: string; amount_rub: number; provider?: string; evidence_version?: number; reliable_money_fact?: boolean | null; effective_evidence_state?: string | null; external_timeline?: { event_id: string; report_id: string; kind: string; at: string }[]; external_report?: { id: string; status: string; review_note: string | null } | null } | null;
  payment_obligations: {
    id: string;
    kind: "advance" | "balance" | "security_deposit";
    amount_rub: number;
    recipient: string;
    due_at: string | null;
    grace_until: string | null;
    required_before_check_in: boolean;
    status: string;
    effective_state: "pending" | "due" | "overdue" | "satisfied" | "not_applicable";
    blocks_check_in: boolean;
  }[];
  messages: {
    id: string;
    kind: string;
    body: string;
    author_side: "customer" | "supplier" | null;
    author_name: string | null;
    actor_role: string | null;
    attribution_status: string;
  }[];
};

type DisputeCase = {
  id: string;
  category: string;
  notes: string;
  status: "open" | "in_review" | "resolved";
  priority: string;
  response_due_at: string | null;
  decision_kind: string | null;
  decision_note: string;
  evidence: { id: string; attachment_id: string; note: string }[];
};

function ackLabel(q: Room["quote"]): string {
  if (q.customer_ack && q.supplier_ack) return "подтверждено обеими сторонами";
  if (q.customer_ack) return "подтвердил только заказчик";
  if (q.supplier_ack) return "подтвердил только исполнитель";
  return "ожидает подтверждений";
}

export default function DealPage() {
  const params = useParams<{ id: string }>();
  const [tab, setTab] = useState<(typeof TABS)[number]["id"]>("summary");
  const [room, setRoom] = useState<Room | null>(null);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const [disputeCategory, setDisputeCategory] = useState("no_show");
  const [disputeNotes, setDisputeNotes] = useState("");
  const [disputes, setDisputes] = useState<DisputeCase[]>([]);
  const [evidenceAttachmentId, setEvidenceAttachmentId] = useState("");
  const [evidenceNote, setEvidenceNote] = useState("");
  const [quoteOpen, setQuoteOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState("");
  const [otpInput, setOtpInput] = useState("");
  const [externalReference, setExternalReference] = useState("");
  const [externalDetails, setExternalDetails] = useState("");
  const [externalCorrectionReason, setExternalCorrectionReason] = useState("wrong_report");
  const [externalCorrectionNote, setExternalCorrectionNote] = useState("");

  async function load() {
    try {
      const [nextRoom, disputeList] = await Promise.all([
        api<Room>(`/deal-room/${params.id}`),
        api<{ items: DisputeCase[] }>(`/bookings/${params.id}/disputes`),
      ]);
      setRoom(nextRoom);
      setDisputes(disputeList.items);
      setError("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Нет доступа");
    }
  }

  useEffect(() => {
    void load();
    trackClientEvent("deal.room.opened", { booking_id: params.id });
  }, [params.id]);

  useEffect(() => {
    if (room?.event_title) document.title = `${room.event_title} · Deal Room · Букер`;
  }, [room?.event_title]);

  useEffect(() => {
    if (!quoteOpen) return;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") setQuoteOpen(false);
    };
    window.addEventListener("keydown", onKeyDown);
    return () => {
      document.body.style.overflow = previousOverflow;
      window.removeEventListener("keydown", onKeyDown);
    };
  }, [quoteOpen]);

  async function act(fn: () => Promise<unknown>) {
    setBusy(true);
    setNotice("");
    try {
      await fn();
      await load();
    } catch (err) {
      setError(err instanceof Error ? err.message : "Ошибка");
    } finally {
      setBusy(false);
    }
  }

  if (!room) {
    return (
      <main>
        <h1>Deal Room</h1>
        {error ? <p>{error}</p> : <div className="skeleton" style={{ minHeight: 220 }} />}
      </main>
    );
  }

  const current = room;
  const side = current.role;
  const accentKind = orgKindToDealRoomAccentKind(current.workspace_kind ?? (side === "customer" ? "customer" : "artist"));
  const people = current.participants ?? [];
  const action = nextAction(current.status);
  const idx = STAGE_ORDER.indexOf(current.status);
  const activeDispute = disputes.find((row) => row.status !== "resolved") ?? null;
  const cleanAttachments = (room.documents ?? []).filter(
    (document) => document.kind === "attachment" && document.scan_status === "clean",
  );
  const inPipeline = idx >= 0;
  const journal = STAGE_ORDER.map((s: string, i: number) => {
    const cls = !inPipeline ? "" : i < idx ? "done" : i === idx ? "now" : "";
    return {
      s,
      cls,
      who: !inPipeline ? "—" : i < idx ? "стороны" : i === idx ? "сейчас" : "дальше",
      result: STATUS_LABEL[s],
      state: !inPipeline ? "не применимо" : iLabel(cls),
    };
  });
  const paymentProvider = current.payment?.provider;
  const isStubPayment = Boolean(current.payment) && (paymentProvider === "stub" || !paymentProvider);
  const isExternalPayment = paymentProvider === "external";

  async function createContract() {
    const result = await api<{
      otp_delivered: boolean;
      otp_delivery?: { customer: boolean; supplier: boolean };
    }>(
      `/bookings/${current.booking_id}/contract`,
      { method: "POST" },
    );
    const deliveredCount = Object.values(result.otp_delivery ?? {}).filter(Boolean).length;
    setNotice(result.otp_delivered
      ? "Коды технического подтверждения отправлены уполномоченным участникам обеих сторон"
      : deliveredCount === 1
        ? "Код доставлен только одной стороне. Второй стороне нужно запросить свой код."
        : "Черновик создан, но коды не доставлены. Запросите код после восстановления канала доставки.");
  }

  async function signContract() {
    if (!current.contract) return;
    let payload: ReturnType<typeof contractDraftAckBody>;
    try {
      payload = contractDraftAckBody(current.contract, otpInput);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Черновик нельзя подтвердить");
      return;
    }
    await act(() =>
      api(`/contracts/${current.contract!.id}/sign`, { method: "POST", body: JSON.stringify(payload) })
    );
    setOtpInput("");
  }

  async function requestContractCode() {
    if (!current.contract) return;
    await act(() => api(`/contracts/${current.contract!.id}/challenge`, { method: "POST" }));
    setNotice("Новый код технического подтверждения отправлен вам");
  }

  async function runNext() {
    if (current.next_action?.kind === "pay_obligation" && current.next_action.obligation_id) {
      const obligationId = current.next_action.obligation_id;
      await act(() =>
        api(`/bookings/${current.booking_id}/payments`, {
          method: "POST",
          body: JSON.stringify({
            idempotency_key: `web-${current.booking_id}-${obligationId}`,
            obligation_id: obligationId,
          }),
        }),
      );
      return;
    }
    if (action.kind === "ack") {
      await act(() => api(`/offers/${current.offer_id}/ack`, { method: "POST", body: JSON.stringify({ quote_id: current.quote.quote_id }) }));
      return;
    }
    if (action.kind === "contract") {
      if (current.contract) {
        await signContract();
      } else {
        await act(() => createContract());
      }
      return;
    }
    if (action.kind === "pay") {
      await act(() =>
        api(`/bookings/${current.booking_id}/payments`, {
          method: "POST",
          body: JSON.stringify({ idempotency_key: `web-${current.booking_id}` }),
        })
      );
      return;
    }
    if (action.kind === "receive") {
      setNotice("Чек-ин откроется в день события — в кабинете и на странице события.");
      return;
    }
    if (action.kind === "operator") {
      window.location.href = "mailto:hello@bukergo.ru?subject=Оператор";
      return;
    }
    setNotice("Действие для этого статуса не требуется. Если что-то пошло не так — напишите оператору: hello@bukergo.ru.");
  }

  function iLabel(cls: string) {
    if (cls === "done") return "зафиксировано";
    if (cls === "now") return "ждёт действия";
    return "не начато";
  }

  const quoteBlock = (
    <div className="quote card">
      <p className="mono">quote_id: {current.quote.quote_id}</p>
      <p>гонорар {money(room.quote.honorarium_rub)}</p>
      <p>
        комиссия {money(room.quote.commission_rub)}{" "}
        {room.quote.commission_rub === 0 ? <span className="chip wait">первая сделка</span> : null}
      </p>
      <p>
        <strong>итого {money(room.quote.total_rub)}</strong>
      </p>
      <p className="timeline">{room.quote.source || "Сумма получена с сервера и связана с этой версией предложения."}</p>
      <p>
        <span className="chip wait">{ackLabel(room.quote)}</span>
      </p>
      {room.hold ? <HoldCountdown expiresAt={room.hold.expires_at} /> : null}
    </div>
  );

  const journalBlock = (
    <>
      {!inPipeline ? (
        <p className="timeline">
          Статус «{STATUS_LABEL[current.status] || current.status}» — вне стандартной цепочки этапов.
        </p>
      ) : null}
      <ul className="journal">
        {journal.map((row: { s: string; cls: string; who: string; result: string; state: string }) => (
          <li key={row.s} className={row.cls}>
            <strong>{row.result}</strong>
            <div className="timeline">
              {row.who} · результат: {row.state}
            </div>
          </li>
        ))}
      </ul>
    </>
  );

  return (
    <main>
      <div className="deal-head">
        <p>
          <Link href="/cabinet">
            К сделкам
          </Link>
        </p>
        <p className="mono">
          {room.booking_id} · {STATUS_LABEL[room.status] || room.status}
        </p>
        <h1>{room.event_title || "Deal Room"}</h1>
        <p>
          Вы{" "}
          {accentKind === "customer"
            ? "заказчик"
            : accentKind === "venue"
              ? "площадка"
              : "исполнитель"}
          . {room.next_step}
        </p>
        {room.event_id ? (
          <p className="timeline">
            <Link href={`/events/${room.event_id}`}>Event Control Room</Link>
          </p>
        ) : null}
        {people.length ? (
          <p className="deal-rail-mobile timeline">
            {people.map((p) => p.name).join(" · ")}
          </p>
        ) : null}
      </div>
      {error ? <p style={{ color: "var(--danger)" }}>{error}</p> : null}
      {notice ? (
        <p className="timeline" role="status">
          {notice}
        </p>
      ) : null}
      <div className="deal-shell">
        <aside className="deal-rail surface-glass">
          <h2>Журнал</h2>
          {journalBlock}
          <h2>Участники</h2>
          {people.map((p) => (
            <p key={p.role}>
              <strong>{p.name}</strong>
              <br />
              <span className="timeline">{p.duty}</span>
            </p>
          ))}
        </aside>
        <section>
          <p className="deal-toolbar" aria-busy={busy} style={busy ? { opacity: 0.55, pointerEvents: "none" } : undefined}>
            <button
              type="button"
              disabled={busy}
              onClick={() =>
                void act(() =>
                  api(`/offers/${room.offer_id}/ack`, { method: "POST", body: JSON.stringify({ side, quote_id: room.quote.quote_id }) })
                )
              }
            >
              Подтвердить условия
            </button>
            <button type="button" className="secondary" onClick={() => void act(() => api(`/bookings/${room.booking_id}/hold`, { method: "POST" }))}>
              Удержать дату
            </button>
            <button type="button" className="secondary" onClick={() => void act(() => createContract())}>
              Создать черновик условий
            </button>
            {room.contract ? (
              <>
                <button
                  type="button"
                  className="secondary"
                  onClick={() => void signContract()}
                >
                  Подтвердить черновик по коду
                </button>
                <button
                  type="button"
                  className="secondary"
                  onClick={() => void requestContractCode()}
                >
                  Запросить новый код
                </button>
              </>
            ) : null}
            <button
              type="button"
              className="secondary"
              onClick={() =>
                void act(() =>
                  api(`/bookings/${room.booking_id}/payments`, {
                    method: "POST",
                    body: JSON.stringify({ idempotency_key: `web-${room.booking_id}` }),
                  })
                )
              }
            >
              Счёт
            </button>
            {isStubPayment && !isExternalPayment ? (
              <>
                {!paymentProvider ? <span className="chip wait">Пилот / без эквайринга</span> : null}
                <button
                  type="button"
                  className="secondary"
                  onClick={() =>
                    void act(() =>
                      api(`/payments/${room.payment!.id}/stub-complete`, {
                        method: "POST",
                        body: JSON.stringify({ status: "succeeded" }),
                      })
                    )
                  }
                >
                  Пилот: отметить оплату
                </button>
              </>
            ) : null}
            {isExternalPayment ? (
              <span className="chip wait" data-testid="external-pay-chip">
                Вне платформы · ждёт оператора
              </span>
            ) : null}
          </p>
          <div className="tabs" role="tablist">
            {TABS.map((item) => (
              <button
                key={item.id}
                type="button"
                role="tab"
                id={`deal-tab-${item.id}`}
                aria-selected={tab === item.id}
                aria-controls={`deal-panel-${item.id}`}
                onClick={() => setTab(item.id)}
              >
                {item.label}
              </button>
            ))}
          </div>
          {tab === "summary" && (
            <div role="tabpanel" id="deal-panel-summary" aria-labelledby="deal-tab-summary">
              <DealRoomSummary accentKind={accentKind} room={room} actionKind={action.kind} />
            </div>
          )}
          {tab === "chat" && (
            <section className="card" role="tabpanel" id="deal-panel-chat" aria-labelledby="deal-tab-chat">
              {room.messages.length === 0 ? (
                <p className="timeline">Сообщений пока нет. Условия предложения доступны справа.</p>
              ) : null}
              {room.messages.map((m) => (
                <div key={m.id} className={`msg ${m.kind === "system" ? "system" : m.kind === "operator" ? "operator" : "chat"}`}>
                  <strong>
                    {m.kind === "system"
                      ? "Букер"
                      : m.kind === "operator"
                        ? "Оператор"
                        : m.attribution_status !== "attributed"
                          ? "Участник (архив)"
                          : `${m.author_side === "customer" ? "Заказчик" : "Исполнитель"}${m.author_name ? ` · ${m.author_name}` : ""}`}:
                  </strong>{" "}
                  {m.body}
                </div>
              ))}
              <form
                className="chat-compose"
                onSubmit={(e) => {
                  e.preventDefault();
                  const body = message.trim();
                  if (!body || busy) return;
                  void act(() =>
                    api(`/deal-room/${room.booking_id}/messages`, {
                      method: "POST",
                      body: JSON.stringify({ body, idempotency_key: crypto.randomUUID() }),
                    }).then(() => setMessage(""))
                  );
                }}
              >
                <input
                  value={message}
                  onChange={(e) => setMessage(e.target.value)}
                  placeholder="Напишите сообщение участникам сделки"
                  aria-label="Сообщение участникам сделки"
                  disabled={busy}
                />
                <button type="submit" disabled={busy || !message.trim()}>
                  Отправить
                </button>
              </form>
              <p>
                <button
                  type="button"
                  className="secondary"
                  onClick={() => {
                    window.location.href = "mailto:hello@bukergo.ru?subject=Оператор%20Deal%20Room";
                  }}
                >
                  Связаться с оператором
                </button>
              </p>
            </section>
          )}
          {tab === "terms" && (
            <section className="card" role="tabpanel" id="deal-panel-terms" aria-labelledby="deal-tab-terms">
              <p>
                Заказчик: {room.quote.customer_ack ? "подтвердил" : "ожидается подтверждение"}. Исполнитель:{" "}
                {room.quote.supplier_ack ? "подтвердил" : "ожидается подтверждение"}.
              </p>
              <p>{ackLabel(room.quote)}. Сообщение в чате не заменяет подтверждение актуальной версии.</p>
            </section>
          )}
          {tab === "documents" && (
            <section className="card" role="tabpanel" id="deal-panel-documents" aria-labelledby="deal-tab-documents">
              {room.documents?.length ? (
                <ul className="timeline">
                  {room.documents.map((doc) => (
                    <li key={`${doc.kind}-${doc.id}`}>
                      {doc.label}
                      {doc.quote_id ? <> · <span className="mono">{doc.quote_id}</span></> : null}
                      {" · "}
                      {doc.kind === "contract" ? contractDraftStatus(doc.signed) : doc.signed ? "подтверждено" : "черновик"}
                    </li>
                  ))}
                </ul>
              ) : null}
              {room.contract ? (
                <>
                  <p className="timeline">
                    Это техническое подтверждение неизменяемого черновика. Юридическая сила простой электронной подписи не утверждена.
                  </p>
                  <p className="mono">quote_id: {room.contract.offer_version_id || "legacy/unbound"}</p>
                  <p className="mono">SHA-256: {room.contract.body_sha256 || "legacy/unbound"}</p>
                  <p className="timeline">
                    Шаблон: {room.contract.template_version}; юридический пакет: {room.contract.legal_pack_version}
                  </p>
                  {room.contract.acknowledgements.length ? (
                    <ul className="timeline">
                      {room.contract.acknowledgements.map((ack) => (
                        <li key={`${ack.side}-${ack.actor_user_id}-${ack.created_at}`}>
                          {ack.side === "customer" ? "Заказчик" : "Исполнитель"}: техническое подтверждение · {formatWhen(ack.created_at)} · {ack.actor_role_snapshot || "роль не зафиксирована"}
                        </li>
                      ))}
                    </ul>
                  ) : null}
                  <pre style={{ whiteSpace: "pre-wrap" }}>{room.contract.body}</pre>
                </>
              ) : "Черновика условий ещё нет"}
            </section>
          )}
          {tab === "payments" && (
            <section className="card" role="tabpanel" id="deal-panel-payments" aria-labelledby="deal-tab-payments">
              <h2>График платежей</h2>
              <ul className="journal">
                {room.payment_obligations.map((obligation) => (
                  <li key={obligation.id} className={obligation.blocks_check_in ? "now" : obligation.effective_state === "satisfied" ? "done" : ""}>
                    <strong>
                      {obligation.kind === "advance" ? "Аванс" : obligation.kind === "balance" ? "Остаток" : "Обеспечительный платёж"}
                      {" · "}{money(obligation.amount_rub)}
                    </strong>
                    <div className="timeline">
                      получатель: {obligation.recipient === "supplier" ? "исполнитель" : obligation.recipient}
                      {obligation.due_at ? ` · срок ${formatWhen(obligation.due_at)}` : " · по выставлению счёта"}
                      {obligation.grace_until ? ` · grace до ${formatWhen(obligation.grace_until)}` : ""}
                      {` · ${obligation.effective_state}`}
                    </div>
                    {obligation.blocks_check_in ? (
                      <p role="alert">Просроченное обязательное начисление блокирует check-in.</p>
                    ) : null}
                  </li>
                ))}
              </ul>
              <p>{room.payment ? `${isExternalPayment ? "Сведения о переводе" : room.payment.status} · ${money(room.payment.amount_rub)}` : "Счёта нет. Статус платежа передаёт платёжный партнёр."}</p>
              {isExternalPayment ? (
                <div className="external-pay-panel" data-testid="external-payment-panel">
                  <p>
                    <span className="chip wait">Оплата вне платформы</span>
                  </p>
                  <p>
                    Перевод идёт напрямую между сторонами. После проверки оператор учтёт сведения о переводе;
                    Букер не получает деньги и не подтверждает банковское зачисление.
                  </p>
                  {room.payment?.status === "external_recorded" ? (
                    <p role="status">Оператор проверил сведения сторон. Банковское зачисление не подтверждено.</p>
                  ) : null}
                  <p role="status">Достоверный денежный факт: не установлен. Отчёт, скриншот и ручная проверка не означают «оплачено».</p>
                  {room.payment?.external_timeline?.length ? (
                    <ol aria-label="Хронология сведений о внешнем переводе">
                      {room.payment.external_timeline.map((entry) => (
                        <li key={entry.event_id}>
                          {entry.kind === "payer_reported" ? "Сообщил плательщик" :
                            entry.kind === "recipient_acknowledged" ? "Подтвердил получатель" :
                            entry.kind === "admin_evidence_reviewed" ? "Проверил оператор" :
                            entry.kind === "correction_requested" ? "Запрошено исправление отметки" :
                            entry.kind === "correction_approved" ? "Отметка исправлена" : "Сведения"}
                          {" · "}{formatWhen(entry.at)}
                        </li>
                      ))}
                    </ol>
                  ) : null}
                  {room.payment?.external_report ? (
                    <p role="status">
                      {room.payment.external_report.status === "submitted" ? "Сведения ожидают проверки оператора." : null}
                      {room.payment.external_report.status === "needs_clarification" ? "Оператор запросил уточнение. Можно отправить новые сведения." : null}
                      {room.payment.external_report.status === "recorded" ? "Сведения проверены оператором; зачисление не установлено." : null}
                      {room.payment.external_report.review_note ? ` ${room.payment.external_report.review_note}` : null}
                    </p>
                  ) : null}
                  {room.role !== "customer" && room.payment?.external_report?.status === "submitted" && !room.payment.external_timeline?.some((entry) => entry.kind === "recipient_acknowledged" && entry.report_id === room.payment?.external_report?.id) ? (
                    <button type="button" className="secondary" disabled={busy} onClick={() => {
                      if (!room.payment?.external_report) return;
                      void act(() => api(`/payments/${room.payment!.id}/external-reports/${room.payment!.external_report!.id}/recipient-ack`, {
                        method: "POST", body: JSON.stringify({ idempotency_key: crypto.randomUUID() }),
                      }));
                    }}>Подтвердить получение сведений о переводе</button>
                  ) : null}
                  {room.payment?.external_report?.status === "recorded" && room.payment.effective_evidence_state === "admin_evidence_reviewed" ? (
                    <form onSubmit={(e) => {
                      e.preventDefault();
                      if (!room.payment?.external_report) return;
                      const target = [...(room.payment.external_timeline ?? [])].reverse().find((entry) => entry.kind === "admin_evidence_reviewed" && entry.report_id === room.payment?.external_report?.id);
                      void act(() => api(`/payments/${room.payment!.id}/external-corrections`, {
                        method: "POST", body: JSON.stringify({
                          report_id: room.payment!.external_report!.id,
                          target_event_id: target?.event_id ?? room.payment!.external_report!.id,
                          reason_code: externalCorrectionReason, note: externalCorrectionNote,
                          expected_version: room.payment!.evidence_version ?? 0,
                          idempotency_key: crypto.randomUUID(),
                        }),
                      }));
                    }}>
                      <label>Причина исправления<select value={externalCorrectionReason} onChange={(e) => setExternalCorrectionReason(e.target.value)}><option value="wrong_report">Неверный отчёт</option><option value="recipient_denied">Получатель не подтвердил</option><option value="duplicate">Дубль</option><option value="partial">Частичный перевод</option><option value="disputed">Спор</option><option value="other">Другая причина</option></select></label>
                      <label>Пояснение без контактов и реквизитов<input minLength={3} maxLength={500} required value={externalCorrectionNote} onChange={(e) => setExternalCorrectionNote(e.target.value)} /></label>
                      <button type="submit" disabled={busy}>Запросить исправление отметки</button>
                    </form>
                  ) : null}
                  {room.role === "customer" && room.payment?.status === "pending" && room.payment.external_report?.status !== "submitted" ? (
                    <form onSubmit={(e) => {
                      e.preventDefault();
                      if (!room.payment) return;
                      const paymentId = room.payment.id;
                      void act(() => api(`/payments/${paymentId}/external-report`, {
                        method: "POST",
                        body: JSON.stringify({
                          idempotency_key: crypto.randomUUID(),
                          reference: externalReference,
                          details: externalDetails,
                        }),
                      }));
                    }}>
                      <label>Номер или реквизиты операции<input required minLength={3} maxLength={128} value={externalReference} onChange={(e) => setExternalReference(e.target.value)} /></label>
                      <label>Пояснение для оператора<input maxLength={1000} value={externalDetails} onChange={(e) => setExternalDetails(e.target.value)} /></label>
                      <button type="submit" disabled={busy}>Отправить сведения на проверку</button>
                    </form>
                  ) : null}
                  {room.payment ? (
                    <p className="mono">
                      payment_id: {room.payment.id} · {room.payment.status} · {money(room.payment.amount_rub)}
                    </p>
                  ) : null}
                  <p>
                    <a
                      className="btn secondary"
                      href={`mailto:hello@bukergo.ru?subject=${encodeURIComponent(
                        `External pay · ${room.booking_id}`,
                      )}&body=${encodeURIComponent(
                        `Booking: ${room.booking_id}\nPayment: ${room.payment?.id || "—"}\nПрошу проверить сведения о внешнем переводе.`,
                      )}`}
                    >
                      Написать оператору
                    </a>
                  </p>
                </div>
              ) : (
                <>
                  {isStubPayment && !paymentProvider ? (
                    <p>
                      <span className="chip wait">Пилот / без эквайринга</span>
                    </p>
                  ) : null}
                  <p>Перевод напрямую не фиксируется платформой.</p>
                </>
              )}
            </section>
          )}
          {tab === "dispute" && (
            <section className="card" role="tabpanel" id="deal-panel-dispute" aria-labelledby="deal-tab-dispute">
              <p>Спор рассматривает оператор. ИИ только помогает сформулировать категорию.</p>
              {disputes.map((row) => (
                <article key={row.id} className="card" aria-label={`Спор ${row.id}`}>
                  <p className="kicker">{row.priority === "urgent" ? "Срочно" : "Высокий приоритет"}</p>
                  <h3>{row.status === "open" ? "Спор открыт" : row.status === "in_review" ? "Оператор рассматривает спор" : "Спор рассмотрен"}</h3>
                  <p>{row.notes || "Комментарий не добавлен."}</p>
                  <p className="timeline">
                    Срок первого ответа: {formatWhen(row.response_due_at)} · доказательств: {row.evidence.length}
                  </p>
                  {row.status === "resolved" ? (
                    <p><strong>Решение:</strong> {row.decision_note || "Решение зафиксировано оператором."}</p>
                  ) : null}
                </article>
              ))}
              {!activeDispute && disputes.length === 0 ? (
                <form
                  onSubmit={(e) => {
                    e.preventDefault();
                    void act(async () => {
                      await api(`/bookings/${room.booking_id}/disputes`, {
                        method: "POST",
                        body: JSON.stringify({ category: disputeCategory, notes: disputeNotes }),
                      });
                      setDisputeNotes("");
                    });
                  }}
                  style={{ display: "grid", gap: 10 }}
                >
                  <label>
                    Категория
                    <select value={disputeCategory} onChange={(e) => setDisputeCategory(e.target.value)}>
                      <option value="no_show">Неявка</option>
                      <option value="delay">Опоздание</option>
                      <option value="quality">Качество услуги</option>
                      <option value="payment">Платёж</option>
                      <option value="cancel">Отмена</option>
                    </select>
                  </label>
                  <label>
                    Что произошло
                    <textarea rows={4} value={disputeNotes} onChange={(e) => setDisputeNotes(e.target.value)} />
                  </label>
                  <button type="submit" disabled={busy}>Открыть спор</button>
                </form>
              ) : null}
              {activeDispute ? (
                <form
                  onSubmit={(event) => {
                    event.preventDefault();
                    if (!evidenceAttachmentId) return;
                    void act(async () => {
                      await api(`/disputes/${activeDispute.id}/evidence`, {
                        method: "POST",
                        body: JSON.stringify({ attachment_id: evidenceAttachmentId, note: evidenceNote }),
                      });
                      setEvidenceAttachmentId("");
                      setEvidenceNote("");
                    });
                  }}
                  style={{ display: "grid", gap: 10, marginTop: 16 }}
                >
                  <h3>Добавить доказательство</h3>
                  {cleanAttachments.length ? (
                    <>
                      <label>
                        Проверенное вложение
                        <select value={evidenceAttachmentId} onChange={(event) => setEvidenceAttachmentId(event.target.value)} required>
                          <option value="">Выберите файл</option>
                          {cleanAttachments.map((document) => (
                            <option key={document.id} value={document.id}>{document.label}</option>
                          ))}
                        </select>
                      </label>
                      <label>
                        Пояснение
                        <input value={evidenceNote} onChange={(event) => setEvidenceNote(event.target.value)} maxLength={2000} />
                      </label>
                      <button type="submit" disabled={busy || !evidenceAttachmentId}>Добавить к спору</button>
                    </>
                  ) : (
                    <p className="timeline">Сначала загрузите документ во вкладке «Документы» и дождитесь безопасной проверки.</p>
                  )}
                </form>
              ) : null}
            </section>
          )}
          {tab === "stages" && (
            <section className="card" role="tabpanel" id="deal-panel-stages" aria-labelledby="deal-tab-stages">
              {journalBlock}
            </section>
          )}
        </section>
        <aside className="deal-aside surface-glass">
          <p className="kicker">Следующий шаг</p>
          <p>{room.next_step}</p>
          <button type="button" aria-busy={busy} disabled={busy} onClick={() => void runNext()}>
            {current.next_action?.label || action.label}
          </button>
          {room.contract && action.kind === "contract" ? (
            <>
              <label>
                Код технического подтверждения черновика
                <input
                  value={otpInput}
                  onChange={(e) => setOtpInput(e.target.value)}
                  inputMode="numeric"
                  autoComplete="one-time-code"
                />
              </label>
              <button type="button" className="secondary" disabled={busy} onClick={() => void requestContractCode()}>
                Запросить новый код
              </button>
            </>
          ) : null}
          {quoteBlock}
        </aside>
      </div>
      <div className="sticky-cta">
        <p className="sticky-next">
          <span className="kicker">Следующее действие</span>
          <span className="timeline">{room.next_step}</span>
        </p>
        <div className="sticky-cta-row">
          <button type="button" className="secondary" onClick={() => setQuoteOpen(true)}>
            Предложение
          </button>
          <button type="button" aria-busy={busy} disabled={busy} onClick={() => void runNext()}>
            {current.next_action?.label || action.label}
          </button>
        </div>
      </div>
      <div className={`sheet-backdrop ${quoteOpen ? "open" : ""}`} onClick={() => setQuoteOpen(false)} />
      <div className={`sheet ${quoteOpen ? "open" : ""}`}>{quoteBlock}</div>
    </main>
  );
}
