import Link from "next/link";
import { ReferencePuzzleHero } from "@/components/ReferencePuzzleHero";
import { HomeSearchForm } from "@/components/HomeSearchForm";

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
    <main className="page-enter immersive-home">
      <script type="application/ld+json" dangerouslySetInnerHTML={{ __html: JSON.stringify(jsonLd) }} />
      <section className="entry-paths" aria-label="С чего начнём"><Link href="/search?kind=artist"><span className="eyebrow">01 / ТОЧНО В ЦЕЛЬ</span><h2>Найти специалиста</h2><p>Диджей, ведущий, фотограф — когда нужен кто-то конкретный.</p><span className="entry-action">Выбрать специалиста ↗</span></Link><Link href="/assemble"><span className="eyebrow">02 / ВСЁ ВМЕСТЕ</span><h2>Собрать событие</h2><p>Место, люди и атмосфера. Ваше событие из хромовых пазлов.</p><span className="entry-action">Начать сборку ↗</span></Link></section><ReferencePuzzleHero />
      <section id="discover" className="discovery-section" aria-labelledby="discover-title">
        <div className="section-heading">
          <div><p className="eyebrow">01 / Найдите своих</p><h2 id="discover-title">Начните с нужной даты</h2></div>
          <p>Артист или площадка?<br />Подберите то, чего не хватает вашей идее.</p>
        </div>
        <div className="discovery-form">
          <HomeSearchForm />
        </div>
        <div className="discovery-links" aria-label="Популярные категории">
          <Link href="/search?kind=artist&city=Москва&category=dj">DJ <span aria-hidden="true">↗</span></Link>
          <Link href="/search?kind=artist&city=Москва&category=host">Ведущие <span aria-hidden="true">↗</span></Link>
          <Link href="/search?kind=artist&city=Москва&category=cover">Кавер-группы <span aria-hidden="true">↗</span></Link>
          <Link href="/search?kind=venue&city=Москва">Площадки <span aria-hidden="true">↗</span></Link>
        </div>
      </section>
      <section className="home-process" aria-labelledby="process-title">
        <div className="section-heading"><div><p className="eyebrow">02 / От идеи к событию</p><h2 id="process-title">Меньше переписок.<br />Больше ясности.</h2></div><Link className="intro-link" href="/assemble">Открыть студию <span aria-hidden="true">↗</span></Link></div>
        <div className="process-grid">
        <article>
          <span className="process-number">01</span><h3>Найдите совпадение</h3>
          <p>Выберите дату, артиста и площадку. Доступность по запросу отмечена отдельно — выбор ещё не означает бронь.</p>
        </article>
        <article>
          <span className="process-number">02</span><h3>Соберите свою команду</h3>
          <p>Участники складываются в карту события. Отправьте заявки и обсудите состав, райдер и детали с каждой стороной.</p>
        </article>
        <article>
          <span className="process-number">03</span><h3>Согласуйте условия</h3>
          <p>Итоговая цена — в предложении. Подтверждения, документы и история договорённостей остаются в комнате сделки.</p>
        </article>
        </div>
      </section>
      <section className="home-supply" aria-labelledby="supply-title">
        <div><p className="eyebrow">По другую сторону сцены</p><h2 id="supply-title">Ваш талант.<br />Чья-то идеальная находка.</h2><p>Выступаете или управляете площадкой? В своём кабинете ведите профиль, календарь и входящие заявки.</p></div>
        <Link className="btn secondary" href="/profile">Мой профиль <span aria-hidden="true">↗</span></Link>
      </section>
      <p className="legal-banner">
        Пилотный запуск: юридические документы дорабатываются, платежи на платформе отключены. <Link href="/legal">Правила сервиса</Link>
      </p>
    </main>
  );
}
