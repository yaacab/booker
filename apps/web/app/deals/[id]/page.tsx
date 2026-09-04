"use client";

import { useEffect, useState } from "react";
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
  payment: { id: string; status: string; amount_rub: number } | null;
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
  const [otpCodes, setOtpCodes] = useState<{ customer?: string; supplier?: string } | null>(null);
  const [otpInput, setOtpInput] = useState("");

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

  // Пилот: коды подписи приходят в ответе POST /bookings/{id}/contract.
  // Восстанавливаем их из sessionStorage, если страницу перезагрузили.
  useEffect(() => {
    const contractId = room?.contract?.id;
    if (!contractId) {
      setOtpCodes(null);
      return;
    }
    try {
      const raw = sessionStorage.getItem(`booker.contractOtp.${contractId}`);
      setOtpCodes(raw ? (JSON.parse(raw) as { customer?: string; supplier?: string }) : null);
    } catch {
      setOtpCodes(null);
    }
  }, [room?.contract?.id]);

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
  // Пилотный код подписи текущей стороны — только если его вернул сервер при создании договора.
  const pilotOtp = side === "customer" ? otpCodes?.customer : otpCodes?.supplier;

  async function createContract() {
    const res = await api<{ id: string; otp_customer?: string; otp_supplier?: string }>(
      `/bookings/${current.booking_id}/contract`,
      { method: "POST" },
    );
    if (res.otp_customer || res.otp_supplier) {
      const codes = { customer: res.otp_customer, supplier: res.otp_supplier };
      setOtpCodes(codes);
      try {
        sessionStorage.setItem(`booker.contractOtp.${res.id}`, JSON.stringify(codes));
      } catch {
        /* ignore */
      }
    }
  }

  async function signContract() {
    if (!current.contract) return;
    const otp = pilotOtp || otpInput.trim();
    if (!otp) {
      setError("Введите код подписи — он показывается при создании договора.");
      return;
    }
    await act(() =>
      api(`/contracts/${current.contract!.id}/sign`, { method: "POST", body: JSON.stringify({ side, otp }) })
    );
    setOtpInput("");
  }

  async function runNext() {
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
                onClick={() => void signContract()}
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
            {room.payment ? (
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
              {otpCodes?.customer || otpCodes?.supplier ? (
                <p className="timeline">
                  <span className="chip wait">код для теста</span> заказчик:{" "}
                  <span className="mono">{otpCodes?.customer ?? "—"}</span>
                  {" · "}исполнитель: <span className="mono">{otpCodes?.supplier ?? "—"}</span>
                </p>
              ) : null}
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
              <p>Перевод напрямую не фиксируется платформой.</p>
              <p>Стороны могут проводить расчёты самостоятельно или по взаимному согласию запросить подключение гаранта.</p>
              <a
                className="btn secondary"
                href={`mailto:hello@bukergo.ru?subject=${encodeURIComponent(`Гарант для сделки ${room.booking_id}`)}`}
              >
                Запросить условия гаранта
              </a>
              <p className="timeline">Вариант начнёт действовать только после отдельного согласия обеих сторон.</p>
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
            {action.label}
          </button>
          {room.contract && action.kind === "contract" ? (
            pilotOtp ? (
              <p className="timeline">
                <span className="chip wait">код для теста</span> <span className="mono">{pilotOtp}</span>
              </p>
            ) : (
              <label>
                Код подписи договора
                <input
                  value={otpInput}
                  onChange={(e) => setOtpInput(e.target.value)}
                  inputMode="numeric"
                  autoComplete="one-time-code"
                />
              </label>
            )
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
            {action.label}
          </button>
        </div>
      </div>
      <div className={`sheet-backdrop ${quoteOpen ? "open" : ""}`} onClick={() => setQuoteOpen(false)} />
      <div className={`sheet ${quoteOpen ? "open" : ""}`}>{quoteBlock}</div>
    </main>
  );
}
