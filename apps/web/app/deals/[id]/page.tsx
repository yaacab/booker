"use client";

import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useParams } from "next/navigation";
import { DealRoomSummary } from "@/components/deal-room/DealRoomSummary";
import { HoldCountdown } from "@/components/HoldCountdown";
import { api, trackClientEvent } from "@/lib/api";
import { orgKindToDealRoomAccentKind } from "@/lib/dealRoomAccents";
import { money } from "@/lib/format";
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
  contract: { id: string; customer_signed: boolean; supplier_signed: boolean; body: string } | null;
  documents?: { kind: string; id: string; label: string; quote_id?: string; signed: boolean }[];
  payment: { id: string; status: string; amount_rub: number; provider?: string } | null;
  messages: { id: string; kind: string; body: string }[];
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
  const [quoteOpen, setQuoteOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState("");
  const [otpInput, setOtpInput] = useState("");
  const quoteRef = useRef<HTMLDivElement>(null);
  const bodyRef = useRef<HTMLDivElement>(null);

  async function load() {
    try {
      setRoom(await api<Room>(`/deal-room/${params.id}`));
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
    const previousFocus = document.activeElement as HTMLElement | null;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    bodyRef.current?.setAttribute("inert", "");
    const frame = requestAnimationFrame(() => quoteRef.current?.querySelector<HTMLButtonElement>("button")?.focus());
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key === "Escape") { event.preventDefault(); setQuoteOpen(false); }
      if (event.key !== "Tab") return;
      const controls = Array.from(quoteRef.current?.querySelectorAll<HTMLElement>('button:not(:disabled), input:not(:disabled), a[href], [tabindex="0"]') || []).filter((el) => el.getClientRects().length > 0);
      const first = controls[0], last = controls[controls.length - 1];
      if (!first) { event.preventDefault(); quoteRef.current?.focus(); return; }
      if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last?.focus(); }
      else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first.focus(); }
    };
    const media = window.matchMedia("(min-width: 1024px)");
    const closeOnDesktop = () => { if (media.matches) setQuoteOpen(false); };
    media.addEventListener("change", closeOnDesktop);
    window.addEventListener("keydown", onKeyDown);
    return () => {
      cancelAnimationFrame(frame);
      document.body.style.overflow = previousOverflow;
      bodyRef.current?.removeAttribute("inert");
      media.removeEventListener("change", closeOnDesktop);
      window.removeEventListener("keydown", onKeyDown);
      if (previousFocus?.isConnected && previousFocus.getClientRects().length) previousFocus.focus({ preventScroll: true });
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
  const bothAgreed=current.quote.customer_ack&&current.quote.supplier_ack;
  const alreadyAgreed=side==="customer"?current.quote.customer_ack:current.quote.supplier_ack;
  const action = current.status==="Negotiation"&&bothAgreed?{kind:"hold",label:"Удержать дату"}:current.status==="Negotiation"&&alreadyAgreed?{kind:"wait",label:"Открыть переписку"}:nextAction(current.status);
  const actionLabel = action.kind === "ack" ? "Подтвердить условия" : action.kind === "contract" ? (current.contract ? "Подписать договор" : "Подготовить договор") : action.kind === "receive" ? "День события" : action.kind === "operator" ? "Связаться с оператором" : action.label;
  const idx = STAGE_ORDER.indexOf(current.status);
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
    await api(`/bookings/${current.booking_id}/contract`, { method: "POST" });
    setNotice("Код подписи отправлен в уведомления");
  }

  async function signContract() {
    if (!current.contract) return;
    const otp = otpInput.trim();
    if (!otp) {
      setError("Введите код подписи из уведомлений.");
      return;
    }
    await act(() =>
      api(`/contracts/${current.contract!.id}/sign`, { method: "POST", body: JSON.stringify({ side, otp }) })
    );
    setOtpInput("");
  }

  async function runNext() {
    if(action.kind==="hold"){
      await act(()=>api(`/bookings/${current.booking_id}/hold`,{method:"POST"}));
      return;
    }
    if(action.kind==="wait"){
      setTab("chat");
      return;
    }
    if (action.kind === "ack") {
      await act(() => api(`/offers/${current.offer_id}/ack`, { method: "POST", body: JSON.stringify({ side }) }));
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
      <div className="deal-quote-heading"><span className="kicker">Текущее предложение</span><span className="deal-quote-marker" aria-hidden="true">↗</span></div>
      <dl className="deal-quote-lines">
        <div><dt>Гонорар</dt><dd>{money(current.quote.honorarium_rub)}</dd></div>
        <div><dt>Комиссия{current.quote.commission_rub === 0 ? <small>Первая сделка</small> : null}</dt><dd>{money(current.quote.commission_rub)}</dd></div>
        <div className="deal-quote-total"><dt>Итого</dt><dd>{money(current.quote.total_rub)}</dd></div>
      </dl>
      <p className="deal-ack-note"><span aria-hidden="true">{current.quote.customer_ack && current.quote.supplier_ack ? "✓" : "◷"}</span>{ackLabel(current.quote)}</p>
      {current.hold ? <HoldCountdown expiresAt={current.hold.expires_at} /> : null}
      <details className="deal-quote-source"><summary>Версия предложения</summary><p className="mono">quote_id: {current.quote.quote_id}</p><p>{current.quote.source || "Стоимость зафиксирована в этой версии предложения."}</p></details>
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
    <main className="deal-reference-page">
      <div ref={bodyRef} className="deal-page-body">
      <header className="deal-head">
        <Link className="deal-back" href="/cabinet">← К списку сделок</Link>
        <div className="deal-title-row"><h1 title={room.booking_id}>Сделка #{room.booking_id.slice(0, 8)}</h1><span className={`chip ${room.status === "Confirmed" || room.status === "Completed" ? "ok" : room.status === "Cancelled" || room.status === "Dispute" ? "bad" : "wait"}`}>{STATUS_LABEL[room.status] || room.status}</span></div>
        <p className="deal-event-title">{room.event_title || "Детали вашего события"}</p>
        <div className="deal-head-meta"><span>Вы — {accentKind === "customer" ? "заказчик" : accentKind === "venue" ? "площадка" : "исполнитель"}</span>{room.event_id ? <Link href={`/events/${room.event_id}`}>К событию <span aria-hidden="true">↗</span></Link> : null}</div>
      </header>
      <ol className="deal-progress" aria-label="Этапы сделки">
        {journal.map((row, index) => <li key={row.s} className={row.cls} aria-current={row.cls === "now" ? "step" : undefined}><span className="deal-progress-dot" aria-hidden="true">{row.cls === "done" ? "✓" : index + 1}</span><strong>{row.result}</strong><small>{row.state}</small></li>)}
      </ol>
      {error ? <p style={{ color: "var(--danger)" }}>{error}</p> : null}
      {notice ? (
        <p className="timeline" role="status">
          {notice}
        </p>
      ) : null}
      <div className="deal-shell">
        <aside className="deal-rail surface-glass">
          <h2>Участники</h2>
          {people.length ? <ul className="deal-people">{people.map((p, index) => <li key={`${p.role}-${index}`}><span className="deal-person-avatar" aria-hidden="true">{p.name.split(/\s+/).filter(Boolean).slice(0, 2).map((part) => part[0]).join("")}</span><span><strong>{p.name}</strong><small>{p.duty}</small></span></li>)}</ul> : <p className="timeline">Участники появятся в сделке после назначения.</p>}
          <p className="deal-participant-note">Условия, документы и сообщения доступны участникам этой сделки.</p>
        </aside>
        <section className="deal-main-panel">
          <details className="deal-actions-menu"><summary>Действия со сделкой <span aria-hidden="true">+</span></summary>
          <p className="deal-toolbar" aria-busy={busy} style={busy ? { opacity: 0.55, pointerEvents: "none" } : undefined}>
            <button
              type="button"
              disabled={busy}
              onClick={() =>
                void act(() =>
                  api(`/offers/${room.offer_id}/ack`, { method: "POST", body: JSON.stringify({ side }) })
                )
              }
            >
              Подтвердить условия
            </button>
            <button type="button" className="secondary" onClick={() => void act(() => api(`/bookings/${room.booking_id}/hold`, { method: "POST" }))}>
              Удержать дату
            </button>
            <button type="button" className="secondary" onClick={() => void act(() => createContract())}>
              Договор
            </button>
            {room.contract ? (
              <button
                type="button"
                className="secondary"
                onClick={() => { if (window.matchMedia("(max-width: 1023px)").matches) setQuoteOpen(true); else void signContract(); }}
              >
                Подписать OTP
              </button>
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
          </details>
          <div className="tabs" role="tablist" aria-label="Разделы сделки">
            {TABS.map((item) => (
              <button
                key={item.id}
                type="button"
                role="tab"
                id={`deal-tab-${item.id}`}
                aria-selected={tab === item.id}
                aria-controls={`deal-panel-${item.id}`}
                tabIndex={tab === item.id ? 0 : -1}
                onKeyDown={(event) => {
                  const index = TABS.findIndex((candidate) => candidate.id === item.id);
                  const next = event.key === "ArrowRight" ? (index + 1) % TABS.length : event.key === "ArrowLeft" ? (index + TABS.length - 1) % TABS.length : event.key === "Home" ? 0 : event.key === "End" ? TABS.length - 1 : -1;
                  if (next < 0) return;
                  event.preventDefault(); setTab(TABS[next].id);
                  document.getElementById(`deal-tab-${TABS[next].id}`)?.focus();
                }}
                onClick={() => setTab(item.id)}
              >
                {item.label}
              </button>
            ))}
          </div>
          {tab === "summary" && (
            <div role="tabpanel" id="deal-panel-summary" aria-labelledby="deal-tab-summary">
              <DealRoomSummary accentKind={accentKind} room={room} actionKind={action.kind} />
              <section className="deal-recent-messages card"><div className="deal-content-heading"><h2>Последние сообщения</h2><button type="button" className="deal-text-link" onClick={() => { setTab("chat"); requestAnimationFrame(() => document.getElementById("deal-tab-chat")?.focus()); }}>Открыть чат ↗</button></div>{room.messages.length ? room.messages.slice(-2).map((item) => <div className={`msg ${item.kind === "system" ? "system" : "chat"}`} key={item.id}><strong>{item.kind === "system" ? "Система" : item.kind === "operator" ? "Оператор" : "Участник"}</strong><p>{item.body}</p></div>) : <p className="timeline">Обсудите с участниками детали события. Переписка останется в сделке.</p>}</section>
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
                    {m.kind === "system" ? "Система" : m.kind === "operator" ? "Оператор" : "Сторона"}:
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
                      body: JSON.stringify({ body }),
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
                      {doc.signed ? "подписано" : "черновик"}
                    </li>
                  ))}
                </ul>
              ) : null}
              <pre style={{ whiteSpace: "pre-wrap" }}>{room.contract?.body || "Договора ещё нет"}</pre>
            </section>
          )}
          {tab === "payments" && (
            <section className="card" role="tabpanel" id="deal-panel-payments" aria-labelledby="deal-tab-payments">
              <p>
                {room.payment
                  ? `${room.payment.status} · ${money(room.payment.amount_rub)}`
                  : "Счёта нет. Статус платежа передаёт платёжный партнёр."}
              </p>
              {isExternalPayment ? (
                <div className="external-pay-panel" data-testid="external-payment-panel">
                  <p>
                    <span className="chip wait">Оплата вне платформы</span>
                  </p>
                  <p>
                    Это <strong>не</strong> онлайн-эквайринг Букера. Перевод идёт напрямую между сторонами; статус
                    «оплачено» выставляет только оператор после ручного подтверждения.
                  </p>
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
                        `Booking: ${room.booking_id}\nPayment: ${room.payment?.id || "—"}\nПрошу подтвердить оплату вне платформы.`,
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
              <form
                onSubmit={(e) => {
                  e.preventDefault();
                  void act(() =>
                    api(`/bookings/${room.booking_id}/disputes`, {
                      method: "POST",
                      body: JSON.stringify({ category: disputeCategory, notes: message }),
                    })
                  );
                }}
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
                <button type="submit">Открыть спор</button>
              </form>
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
            {actionLabel}
          </button>
          {room.contract && action.kind === "contract" ? (
            <label>
              Код подписи договора
              <input
                value={otpInput}
                onChange={(e) => setOtpInput(e.target.value)}
                inputMode="numeric"
                autoComplete="one-time-code"
              />
            </label>
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
          <button type="button" aria-busy={busy} disabled={busy} onClick={() => { if (room.contract && action.kind === "contract") setQuoteOpen(true); else void runNext(); }}>
            {actionLabel}
          </button>
        </div>
      </div>
      </div>
      {quoteOpen ? <button type="button" className="sheet-backdrop open" aria-label="Закрыть предложение" onClick={() => setQuoteOpen(false)} /> : null}
      <div ref={quoteRef} tabIndex={-1} role="dialog" aria-hidden={!quoteOpen} aria-modal={quoteOpen ? true : undefined} aria-labelledby="deal-quote-dialog-title" className={`sheet ${quoteOpen ? "open" : ""}`}>
        <div className="deal-sheet-head"><h2 id="deal-quote-dialog-title">Предложение</h2><button type="button" aria-label="Закрыть предложение" onClick={() => setQuoteOpen(false)}>×</button></div>
        {quoteBlock}
        {room.contract && action.kind === "contract" ? <label>Код подписи договора<input value={otpInput} onChange={(e) => setOtpInput(e.target.value)} inputMode="numeric" autoComplete="one-time-code" /></label> : null}
        <button type="button" className="deal-sheet-action" disabled={busy} aria-busy={busy} onClick={() => void runNext()}>{actionLabel}</button>
        {error ? <p role="alert" className="deal-sheet-error">{error}</p> : null}
      </div>
    </main>
  );
}
