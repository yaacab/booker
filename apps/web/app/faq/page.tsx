"use client";

import Link from "next/link";
import { useState } from "react";

const ITEMS = [
  {
    t: "А сколько это будет?",
    b: "Сервер скажет. Вы — нет. На экране номер цены, не скрин из Excel и не «ну примерно».",
  },
  {
    t: "Первая сделка правда бесплатная?",
    b: "Комиссию платформы на первую сделку заказчика в контуре обнуляем. Гонорар как обычно: мы не Дед Мороз. Прямой перевод «на карту как друзья» в подарок не входит.",
  },
  {
    t: "Одного «ок» мало?",
    b: "Мало. Сделка живёт, когда кивнули обе стороны. Лайк в чате юридической силы не имеет, как бы ни хотелось.",
  },
  {
    t: "Что за hold?",
    b: "Короткий замок на дату. Просрочили — слот снова гуляет. Таймер не салютует, он просто отбирает игрушку.",
  },
  {
    t: "Вы сами сыграете?",
    b: "Нет. Договор сторон лежит в гримёрке сделки. Мы агрегатор: бумажки, не бэк-вокал.",
  },
  {
    t: "Когда платить?",
    b: "Когда появится партнёр и юрист кивнёт. Сейчас пилот: статус рисует заглушка, не эквайринг. Не путать с «уже оплачено».",
  },
  {
    t: "Передумали?",
    b: "Считается то, что в подписанной версии. «Ну мы же в вотсапе договорились» — милый жанр, не документ.",
  },
  {
    t: "Если все поругались?",
    b: "Категория из списка, решение — человек. Нейронке лицензию на скандал не выдавали. Правила — в спорах.",
  },
  {
    t: "А если кину на карту напрямую?",
    b: "Романтика. Нас там нет. Сопровождение по этой брони снимаем — без обиды, почти.",
  },
];

export default function FaqPage() {
  const [asked, setAsked] = useState("");
  const jsonLd = {
    "@context": "https://schema.org",
    "@type": "FAQPage",
    mainEntity: ITEMS.map((item) => ({
      "@type": "Question",
      name: item.t,
      acceptedAnswer: { "@type": "Answer", text: item.b },
    })),
  };
  return (
    <main className="page-enter">
      <script type="application/ld+json" dangerouslySetInnerHTML={{ __html: JSON.stringify(jsonLd) }} />
      <p className="kicker">Без воды. Почти.</p>
      <h1>Как это едет</h1>
      <div className="accordion">
        {ITEMS.map((item) => (
          <details key={item.t}>
            <summary>{item.t}</summary>
            <p>{item.b}</p>
          </details>
        ))}
      </div>
      <article className="card" style={{ marginTop: 20 }}>
        <h2>Бот, который не судья</h2>
        <p className="timeline">Может ткнуть носом в раздел. Вердикт по спору не пишет — характера хватает и без этого.</p>
        <label>
          Что непонятно
          <textarea rows={3} value={asked} onChange={(e) => setAsked(e.target.value)} />
        </label>
        <p className="timeline">
          {asked
            ? "Черновик: листайте пункты выше или зовите человека. Это не решение спора, даже если звучит уверенно."
            : null}
        </p>
        <p style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
          <a className="btn" href="mailto:hello@bukergo.ru?subject=Оператор">
            Позвать человека
          </a>
          <Link className="btn secondary" href="/legal">
            Мелкий шрифт
          </Link>
        </p>
      </article>
    </main>
  );
}
