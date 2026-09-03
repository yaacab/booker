"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { money } from "@/lib/format";

const TABS = [
  { id: "summary", label: "Сводка" },
  { id: "chat", label: "Чат" },
  { id: "terms", label: "Условия" },
  { id: "documents", label: "Документы" },
  { id: "payments", label: "Платежи" },
  { id: "dispute", label: "Спор" },
  { id: "stages", label: "Этапы" },
] as const;

const PEOPLE = [
  { name: "Студия события", duty: "заказчик · условия и оплата" },
  { name: "Nova Show", duty: "исполнитель · дата и сет" },
  { name: "Букер", duty: "агрегатор · статус и история сделки" },
];

export default function DealRoomDemoPage() {
  const [tab, setTab] = useState<(typeof TABS)[number]["id"]>("summary");
  const [quoteOpen, setQuoteOpen] = useState(false);
  const [guarantorOpen, setGuarantorOpen] = useState(false);
  const [assistantOpen, setAssistantOpen] = useState(false);
  const [guarantorChoice, setGuarantorChoice] = useState<"off" | "proposed">("off");
  const [files, setFiles] = useState<string[]>([]);
  const [messages, setMessages] = useState<string[]>([]);
  const [message, setMessage] = useState("");

  useEffect(() => {
    if (!quoteOpen && !guarantorOpen && !assistantOpen) return;
    const previousOverflow = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key !== "Escape") return;
      setQuoteOpen(false);
      setGuarantorOpen(false);
      setAssistantOpen(false);
    };
    window.addEventListener("keydown", onKeyDown);
    return () => {
      document.body.style.overflow = previousOverflow;
      window.removeEventListener("keydown", onKeyDown);
    };
  }, [quoteOpen, guarantorOpen, assistantOpen]);
  return (
    <main>
      <div className="deal-head">
        <p>
          <Link href="/">
            На главную
          </Link>
        </p>
        <p className="mono">BK-DEMO</p>
        <h1>Deal Room</h1>
        <p>Условия, сообщения, документы и отдельные подтверждения каждой стороны.</p>
        <p className="deal-rail-mobile timeline">Студия события · Nova Show · Букер</p>
      </div>
      <div className="deal-shell">
        <aside className="deal-rail surface-glass">
          <h2>Этапы</h2>
          <ul className="journal">
            <li className="done">
              <strong>Заявка создана</strong>
              <div className="timeline">система · зафиксировано</div>
            </li>
            <li className="now">
              <strong>Ожидает подтверждения</strong>
              <div className="timeline">площадка · требуется действие</div>
            </li>
          </ul>
          <h2>Участники</h2>
          {PEOPLE.map((p) => (
            <p key={p.name}>
              <strong>{p.name}</strong>
              <br />
              <span className="timeline">{p.duty}</span>
            </p>
          ))}
        </aside>
        <section>
          <div className="tabs" role="tablist">
            {TABS.map((item) => (
              <button
                key={item.id}
                type="button"
                role="tab"
                aria-selected={tab === item.id}
                onClick={() => setTab(item.id)}
              >
                {item.label}
              </button>
            ))}
          </div>
          {tab === "summary" && (
            <div className="card">
              <p className="kicker">Сводка сделки</p>
              <p className="timeline">Демо-событие · BK-DEMO</p>
              <p>
                Статус брони: <strong>Ожидает подтверждения</strong>
              </p>
              <p>
                <span className="kicker">Следующее действие</span>
                <br />
                Подтвердить условия обеими сторонами
              </p>
            </div>
          )}
          {tab === "chat" && (
            <div className="card">
              <div className="msg system">
                Система: серверное предложение отправлено участникам сделки.
              </div>
              <div className="msg operator">Оператор: проверяю изменения райдера и состав участников.</div>
              {messages.map((item, index) => <div className="msg chat" key={`${item}-${index}`}>Вы: {item}</div>)}
              <form
                className="chat-compose"
                onSubmit={(event) => {
                  event.preventDefault();
                  const value = message.trim();
                  if (!value) return;
                  setMessages((current) => [...current, value]);
                  setMessage("");
                }}
              >
                <label>
                  Сообщение
                  <input value={message} maxLength={2000} onChange={(event) => setMessage(event.target.value)} placeholder="Напишите сообщение участникам" />
                </label>
                <button type="submit">Отправить</button>
              </form>
            </div>
          )}
          {tab === "terms" && (
            <div className="card">
              <p>Версия условий считается принятой только после отдельных подтверждений заказчика и исполнителя.</p>
            </div>
          )}
          {tab === "documents" && (
            <div className="card">
              <p>Документы и райдеры привязаны к сделке и сохраняются в истории изменений.</p>
              <label className="file-drop">
                <strong>Добавить файл</strong>
                <span className="timeline">PDF, DOCX, JPG или PNG · до 20 МБ</span>
                <input
                  type="file"
                  multiple
                  accept=".pdf,.doc,.docx,.jpg,.jpeg,.png"
                  onChange={(event) => setFiles((current) => [...current, ...Array.from(event.target.files || []).map((file) => file.name)])}
                />
              </label>
              {files.map((file, index) => <p className="file-row" key={`${file}-${index}`}><span>{file}</span><button type="button" className="secondary" onClick={() => setFiles((current) => current.filter((_, itemIndex) => itemIndex !== index))}>Удалить</button></p>)}
            </div>
          )}
          {tab === "payments" && (
            <div className="card">
              <p>Стороны могут провести расчёты самостоятельно или по взаимному согласию подключить гаранта.</p>
              <p>Прямой перевод вне предусмотренного сценария платформой не фиксируется.</p>
              <button type="button" className="secondary" onClick={() => setGuarantorOpen(true)}>Выбрать способ расчёта</button>
            </div>
          )}
          {tab === "dispute" && (
            <div className="card">
              <p>Помощник соберёт номер сделки, спорный пункт, сообщения и файлы. Решение принимает оператор.</p>
              <button type="button" className="secondary" onClick={() => setAssistantOpen(true)}>
                Открыть помощника
              </button>
            </div>
          )}
          {tab === "stages" && (
            <div className="card">
              <ul className="journal">
                <li className="done">
                  <strong>Заявка создана</strong>
                  <div className="timeline">система · зафиксировано</div>
                </li>
                <li className="now">
                  <strong>Ожидает площадку</strong>
                  <div className="timeline">серверный статус · требуется действие</div>
                </li>
              </ul>
            </div>
          )}
        </section>
        <aside className="deal-aside surface-glass">
          <p className="kicker">Следующий шаг</p>
          <button type="button">Подтвердить условия</button>
          <div className="quote card">
            <p className="mono">quote_id: demo-quote</p>
            <p>гонорар {money(100000)}</p>
            <p>
              комиссия {money(0)} <span className="chip wait">первая сделка</span>
            </p>
            <p>
              <strong>итого {money(100000)}</strong>
            </p>
            <p className="timeline">Первая сделка: комиссия платформы 0. Сумма получена с сервера.</p>
          </div>
          <p className="timeline">Hold появится после взаимного ack. Таймер не пульсирует.</p>
          <div className="card" style={{ marginTop: 12 }}>
            <strong>{guarantorChoice === "proposed" ? "Гарант предложен" : "Гарант не подключён"}</strong>
            <p className="timeline">Способ расчёта меняется только после согласия второй стороны.</p>
            <button type="button" className="secondary" onClick={() => setGuarantorOpen(true)}>Настроить</button>
          </div>
        </aside>
      </div>
      <div className="sticky-cta">
        <p className="sticky-next">
          <span className="kicker">Следующее действие</span>
          <span className="timeline">Подтвердить условия обеими сторонами</span>
        </p>
        <div className="sticky-cta-row">
          <button type="button" className="secondary" onClick={() => setQuoteOpen(true)}>
            Предложение
          </button>
          <button type="button">Подтвердить</button>
        </div>
      </div>
      <div className={`sheet-backdrop ${quoteOpen ? "open" : ""}`} onClick={() => setQuoteOpen(false)} />
      <div className={`sheet ${quoteOpen ? "open" : ""}`}>
        <p className="mono">quote_id: demo-quote</p>
        <p>
          комиссия {money(0)} <span className="chip wait">первая сделка</span>
        </p>
        <p>итого {money(100000)}</p>
      </div>
      {guarantorOpen ? (
        <div className="modal-layer" role="presentation" onMouseDown={() => setGuarantorOpen(false)}>
          <section className="modal-card" role="dialog" aria-modal="true" aria-labelledby="guarantor-title" onMouseDown={(event) => event.stopPropagation()}>
            <h2 id="guarantor-title">Способ расчёта</h2>
            <p className="timeline">Изменение вступит в силу только после отдельного согласия второй стороны.</p>
            <button type="button" className={`role-option ${guarantorChoice === "off" ? "on" : ""}`} onClick={() => setGuarantorChoice("off")}><span><strong>Без гаранта</strong><small>Стороны проводят расчёты самостоятельно</small></span><span>{guarantorChoice === "off" ? "✓" : ""}</span></button>
            <button type="button" className={`role-option ${guarantorChoice === "proposed" ? "on" : ""}`} onClick={() => setGuarantorChoice("proposed")}><span><strong>Предложить гаранта</strong><small>Вторая сторона получит отдельный запрос</small></span><span>{guarantorChoice === "proposed" ? "✓" : ""}</span></button>
            <p className="wizard-actions"><button type="button" className="secondary" onClick={() => setGuarantorOpen(false)}>Отмена</button><button type="button" onClick={() => setGuarantorOpen(false)}>Сохранить выбор</button></p>
          </section>
        </div>
      ) : null}
      {assistantOpen ? (
        <div className="modal-layer" role="presentation" onMouseDown={() => setAssistantOpen(false)}>
          <section className="modal-card" role="dialog" aria-modal="true" aria-labelledby="assistant-title" onMouseDown={(event) => event.stopPropagation()}>
            <p className="kicker">Букер AI</p>
            <h2 id="assistant-title">Собрать контекст для оператора</h2>
            <div className="msg system">Сделка ожидает подтверждения площадки. Текущий quote_id остаётся действующим до новой серверной версии.</div>
            <p className="timeline">Помощник объясняет статус и структурирует факты, но не меняет условия и не принимает решение.</p>
            <p className="wizard-actions"><button type="button" className="secondary" onClick={() => setAssistantOpen(false)}>Закрыть</button><button type="button" onClick={() => setAssistantOpen(false)}>Передать оператору</button></p>
          </section>
        </div>
      ) : null}
    </main>
  );
}
