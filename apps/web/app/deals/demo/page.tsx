"use client";

import { useState } from "react";
import Link from "next/link";
import { money } from "@/lib/format";

const TABS = [
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
  { name: "Букер", duty: "агрегатор. На бис не выходим" },
];

export default function DealRoomDemoPage() {
  const [tab, setTab] = useState<(typeof TABS)[number]["id"]>("chat");
  const [quoteOpen, setQuoteOpen] = useState(false);
  return (
    <main>
      <div className="deal-head">
        <p>
          <Link href="/">
            На главную
          </Link>
        </p>
        <p className="mono">BK-DEMO</p>
        <h1>Гримёрка сделки</h1>
        <p>Дальше — кивнуть с двух сторон. Один лайк не считается.</p>
        <p className="deal-rail-mobile timeline">Студия события · Nova Show · Букер</p>
      </div>
      <div className="deal-shell">
        <aside className="deal-rail">
          <h2>Журнал</h2>
          <ul className="journal">
            <li className="done">
              <strong>Заявка создана</strong>
              <div className="timeline">система · зафиксировано</div>
            </li>
            <li className="now">
              <strong>Согласование</strong>
              <div className="timeline">стороны · ждёт действия</div>
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
          {tab === "chat" && (
            <div className="card">
              <div className="msg system">
                Система: привезли предложение. Цифру считает только сервер — не спорьте с калькулятором.
              </div>
              <div className="msg operator">Оператор: райдер уточню. По спору нейронкой не прикидываюсь.</div>
            </div>
          )}
          {tab === "terms" && (
            <div className="card">
              <p>Версия живёт после ack заказчика и исполнителя. Один «ок» в чате — просто шум.</p>
            </div>
          )}
          {tab === "documents" && (
            <div className="card">
              <p>Черновик договора. Букер — агрегатор. На сцену сами не лезем, честно.</p>
            </div>
          )}
          {tab === "payments" && (
            <div className="card">
              <p>Оплата через партнёра. Прямой перевод снимает защиту — романтика остаётся вам.</p>
              <p>Статус платежа передаёт платёжный партнёр.</p>
            </div>
          )}
          {tab === "dispute" && (
            <div className="card">
              <p>Категории: неявка, опоздание, качество, платёж, отмена. Решение — оператор, не ИИ. У нейронки нет допуска за кулисы.</p>
              <button type="button" className="secondary">
                Позвать человека
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
                  <strong>Согласование</strong>
                  <div className="timeline">стороны · ждёт действия</div>
                </li>
              </ul>
            </div>
          )}
        </section>
        <aside className="deal-aside">
          <p className="kicker">Следующий ход</p>
          <button type="button">Кивнуть условиям</button>
          <div className="quote card">
            <p className="mono">quote_id: demo-quote</p>
            <p>гонорар {money(100000)}</p>
            <p>
              комиссия {money(0)} <span className="chip wait">первая сделка</span>
            </p>
            <p>
              <strong>итого {money(100000)}</strong>
            </p>
            <p className="timeline">Первая сделка: комиссия платформы 0. Гонорар как есть. Цифру собрал сервер.</p>
          </div>
          <p className="timeline">Hold появится после взаимного ack. Таймер не пульсирует.</p>
        </aside>
      </div>
      <div className="sticky-cta">
        <button type="button" className="secondary" onClick={() => setQuoteOpen(true)}>
          Цифра
        </button>
        <button type="button">Кивнуть условиям</button>
      </div>
      <div className={`sheet-backdrop ${quoteOpen ? "open" : ""}`} onClick={() => setQuoteOpen(false)} />
      <div className={`sheet ${quoteOpen ? "open" : ""}`}>
        <p className="mono">quote_id: demo-quote</p>
        <p>
          комиссия {money(0)} <span className="chip wait">первая сделка</span>
        </p>
        <p>итого {money(100000)}</p>
      </div>
    </main>
  );
}
