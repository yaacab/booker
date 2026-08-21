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
      <p className="kicker">Не доска объявлений. И не караоке для менеджеров.</p>
      <h1>Пока вы миритесь в чате, дата уже чужая.</h1>
      <p>
        Букер держит слот, цифру и подписи в одной комнате. На сцену не выходим — голос не тот.
        Цену не рисуем маркером: её считает сервер.
      </p>
      <form className="search" action="/search" method="get">
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
            <option value="cover">Кавер</option>
            <option value="venue">Площадка</option>
          </select>
        </label>
        <button type="submit">Кто ещё не занят</button>
      </form>
      <p className="timeline">Пилот: в каталоге живые слоты пока из Москвы.</p>
      <p className="legal-banner" style={{ marginTop: 20 }}>
        Оферта ещё черновик, эквайринг выключен. Первая сделка в контуре — комиссия платформы 0, гонорар как есть.
        {" "}
        <Link href="/legal">Бумажки</Link>
      </p>
      <article className="card tint" style={{ marginTop: 28 }}>
        <p className="kicker">Для новых</p>
        <h2>Первый заход — нашу долю оставляете себе</h2>
        <p>
          Гонорар артисту как обычно: мы не Дед Мороз. Комиссию платформы на первую сделку в контуре
          обнуляем. Прямой перевод на карту «как друзья» в подарок не входит.
        </p>
      </article>
      <div className="grid" style={{ marginTop: 32 }}>
        <article className="card">
          <h2>Цифра без фокуса</h2>
          <p>Калькулятор в голове — мило. В договоре — нет. Приезжает номер цены с сервера.</p>
        </article>
        <article className="card">
          <h2>Одна дата — один хозяин</h2>
          <p>Hold с таймером. Проспали — слот снова гуляет. Два «да» на одну пятницу мы не выдаём.</p>
        </article>
        <article className="card">
          <h2>Нейронка в судьи не идёт</h2>
          <p>Скандал разбирает человек. Мы не страховая, не кавер-группа и не ваш семейный чат.</p>
        </article>
      </div>
      <p style={{ marginTop: 28, display: "flex", gap: 8, flexWrap: "wrap" }}>
        <Link className="btn" href="/events/new">
          Собрать вечер
        </Link>
        <Link className="btn secondary" href="/deals/demo">
          Подсмотреть гримёрку
        </Link>
      </p>
    </main>
  );
}
