import Link from "next/link";
import { CityField } from "@/components/CityField";
import { moscowToday } from "@/lib/format";

export const metadata = {
  alternates: { canonical: "/" },
};

export default function HomePage() {
  const jsonLd = {
    "@context": "https://schema.org",
    "@graph": [
      {
        "@type": "Organization",
        name: "Букер",
        url: "https://bukergo.ru",
        email: "hello@bukergo.ru",
        description: "Агрегатор сделки: слот, цифра с сервера и подписи. Не исполнитель выступления.",
      },
      {
        "@type": "WebSite",
        name: "Букер",
        url: "https://bukergo.ru",
        inLanguage: "ru",
      },
    ],
  };
  return (
    <main className="page-enter hero">
      <script type="application/ld+json" dangerouslySetInnerHTML={{ __html: JSON.stringify(jsonLd) }} />
      <section className="hero-grid">
        <div className="hero-copy">
          <p className="kicker">Backstage Control Room</p>
          <h1>Соберите событие. Мы сведём стороны в одной сделке.</h1>
          <p>
            Дата, свободный слот, райдер, предложение и подтверждения — в спокойном профессиональном интерфейсе.
          </p>
          <ul className="hero-checks">
            <li>Цена появляется только в серверном предложении</li>
            <li>Состав события — роли, каждая со своей сделкой</li>
            <li>Каждая сторона подтверждает условия отдельно</li>
            <li>История сделки сохраняется в Deal Room</li>
          </ul>
        </div>
        <aside className="hero-search card surface-glass">
          <p className="kicker">Поиск по календарю</p>
          <h2>Найдите свободный слот</h2>
          <p className="timeline">Сначала дата и формат — затем доступные участники.</p>
          <form className="search search-vertical" action="/search" method="get">
            <CityField name="city" defaultValue="Москва" />
            <label>
              Дата
              <input name="date" type="date" min={moscowToday()} />
            </label>
            <label>
              Кто нужен
              <select name="category" defaultValue="dj">
                <option value="dj">DJ</option>
                <option value="host">Ведущий</option>
                <option value="cover">Кавер-группа</option>
                <option value="venue">Площадка</option>
              </select>
            </label>
            <button type="submit">Показать свободных</button>
          </form>
          <p className="timeline">Пилотный каталог сейчас работает по Москве.</p>
        </aside>
      </section>
      <p className="legal-banner" style={{ marginTop: 20 }}>
        Юридические документы находятся в режиме пилота, проведение платежей пока отключено.
        {" "}
        <Link href="/legal">Подробнее о правилах сервиса</Link>
      </p>
      <div className="grid" style={{ marginTop: 32 }}>
        <article className="card">
          <p className="kicker">01 · Предложение</p>
          <h2>Сумма связана с quote_id</h2>
          <p>Каталог показывает ориентир. Итоговые условия поступают с сервера и фиксируются отдельной версией.</p>
        </article>
        <article className="card">
          <p className="kicker">02 · Календарь</p>
          <h2>Один ресурс — один слот</h2>
          <p>Временное удержание имеет срок действия. После его окончания дата снова становится доступной.</p>
        </article>
        <article className="card">
          <p className="kicker">03 · Поддержка</p>
          <h2>ИИ объясняет, оператор решает</h2>
          <p>Помощник структурирует факты и статусы. Решения по спорным вопросам принимает оператор.</p>
        </article>
      </div>
      <p style={{ marginTop: 28, display: "flex", gap: 8, flexWrap: "wrap" }}>
        <Link className="btn btn-glass" href="/events/new">
          Создать заявку
        </Link>
        <Link className="btn secondary btn-glass" href="/deals/demo">
          Посмотреть Deal Room
        </Link>
      </p>
    </main>
  );
}
