"use client";

import Link from "next/link";
import { useState } from "react";

const ITEMS = [
  {
    t: "Где посмотреть итоговую стоимость?",
    b: "Каталог показывает ориентир. Итоговая стоимость, состав услуг и условия отображаются в предложении внутри сделки. Проверьте их перед подтверждением.",
  },
  {
    t: "Как переключить роль заказчика, исполнителя или площадки?",
    b: "В шапке есть переключатель рабочего пространства. Выберите организацию нужного типа — кабинет покажет заявки и действия этой роли. Один вход может относиться к нескольким пространствам.",
  },
  {
    t: "Можно ли указать несколько ролей в одном событии?",
    b: "Да. Состав события — это список ролей на дату: несколько позиций в одной заявке. Это ещё не бронь и не расчёт суммы.",
  },
  {
    t: "Это одна сделка на весь состав?",
    b: "Нет. Каждая роль оформляется отдельной сделкой со своим Deal Room, предложением и подтверждениями сторон.",
  },
  {
    t: "Почему сумма не считается на экране состава?",
    b: "В составе события вы планируете команду и бюджет. Точная стоимость появляется в предложении внутри сделки после согласования услуг.",
  },
  {
    t: "Как работает комиссия первой сделки?",
    b: "Если серверное предложение показывает нулевую комиссию платформы, это относится только к комиссии Букера. Гонорар исполнителя и остальные условия сохраняются.",
  },
  {
    t: "Почему нужны два подтверждения?",
    b: "Заказчик и исполнитель подтверждают одну и ту же версию условий отдельно. Сообщение в чате не заменяет это действие.",
  },
  {
    t: "Что означает удержание даты?",
    b: "Это временная фиксация слота с указанным сроком. После истечения срока слот снова становится доступным, если сделка не перешла дальше.",
  },
  {
    t: "Кем выступает Букер в сделке?",
    b: "Букер объединяет заявку, предложение, сообщения, документы и статусы. Услугу оказывает выбранный исполнитель или площадка.",
  },
  {
    t: "Когда станет доступен платёжный сценарий?",
    b: "В пилотной версии платёжный сценарий отключён. Активный статус появится только после подключения партнёра и юридической проверки.",
  },
  {
    t: "Как изменить согласованные условия?",
    b: "Изменение создаёт новую версию предложения. Стороны видят историю и подтверждают актуальную версию отдельно.",
  },
  {
    t: "Кто рассматривает спор?",
    b: "Обращение рассматривает оператор по правилам сервиса и материалам сделки. Букер сохраняет договорённости и статусы; сторонам важно приложить описание ситуации и подтверждающие материалы.",
  },
  {
    t: "Что происходит при прямом переводе?",
    b: "Перевод вне предусмотренного сценария не фиксируется платформой. Сторонам важно учитывать это при выборе способа расчёта.",
  },
  {
    t: "Можно ли привлечь гаранта?",
    b: "Да, если обе стороны выбрали этот вариант и отдельно подтвердили условия. До взаимного согласия способ расчёта не меняется.",
  },
  {
    t: "Что такое буфер слота?",
    b: "Минуты до и после выступления, которые нельзя пересечь другим слотом того же исполнителя или зала. Нулевые буферы не меняют прежнее поведение календаря.",
  },
];

export default function FaqPage() {
  const [query, setQuery] = useState("");
  const [group, setGroup] = useState("all");
  const groups = [{ id: "all", title: "Все", indices: ITEMS.map((_, i) => i) },
    { id: "customer", title: "Для заказчиков", indices: [0, 2, 3, 4, 5, 6, 8, 9, 11, 12, 13] },
    { id: "artist", title: "Для артистов", indices: [1, 5, 6, 7, 8, 9, 10, 11, 14] },
    { id: "venue", title: "Для площадок", indices: [1, 3, 6, 7, 8, 9, 10, 11, 14] }];
  const normalized = query.trim().toLocaleLowerCase("ru").replaceAll("ё", "е");
  const selected = groups.find((item) => item.id === group)!;
  const visible = ITEMS.filter((item, i) => selected.indices.includes(i) && `${item.t} ${item.b}`.toLocaleLowerCase("ru").replaceAll("ё", "е").includes(normalized));
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
    <main className="page-enter reference-information faq-reference">
      <script type="application/ld+json" dangerouslySetInnerHTML={{ __html: JSON.stringify(jsonLd) }} />
      <header className="information-heading"><p className="kicker">Помощь</p>
      <h1>Вопросы<br />и ответы</h1><p>Ответы на частые вопросы о Букере.<br />Если не нашли нужную информацию — напишите нам.</p></header>
      <form className="faq-search" role="search" onSubmit={(event) => event.preventDefault()}>
        <label htmlFor="faq-search">Найти ответ</label><input id="faq-search" type="search" placeholder="Например, как подтвердить условия" value={query} onChange={(event) => setQuery(event.target.value)} />
        {query && <button type="button" className="secondary" onClick={() => setQuery("")}>Сбросить</button>}
      </form>
      <div className="faq-categories" role="group" aria-label="Для кого вопрос">{groups.map((item) => <button key={item.id} type="button" className={group === item.id ? "selected" : "secondary"} aria-pressed={group === item.id} onClick={() => setGroup(item.id)}>{item.title}</button>)}</div>
      <p className="faq-result-count" role="status">Найдено ответов: {visible.length}</p>
      <div className="accordion">
        {visible.map((item) => (
          <details key={item.t}>
            <summary>{item.t}</summary>
            <p>{item.b}</p>
          </details>
        ))}
      </div>
      {!visible.length && <div className="card"><h2>Такой ответ пока не найден</h2><p>Попробуйте другие слова или передайте вопрос в поддержку.</p></div>}
      <aside className="information-help"><div><h2>Остались вопросы?</h2><p>Поможем разобраться с вашим событием.</p></div><Link className="btn" href="/support">Написать в поддержку →</Link></aside>
    </main>
  );
}
