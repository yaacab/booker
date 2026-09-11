import Link from "next/link";
import ArtistFirstHero from "@/components/ArtistFirstHero";
export const metadata = { alternates: { canonical: "/" } };
export default function HomePage() {
  return <main className="page-enter immersive-home artist-first-home">
    <script type="application/ld+json" dangerouslySetInnerHTML={{__html:JSON.stringify({"@context":"https://schema.org","@graph":[{"@type":"Organization",name:"Букер",url:"https://bukergo.ru",email:"hello@bukergo.ru",description:"Сервис поиска артистов и работы для артистов. Согласование условий и сопровождение сделки."},{"@type":"WebSite",name:"Букер",url:"https://bukergo.ru",inLanguage:"ru"}]})}}/>
    <ArtistFirstHero />
    <section className="discovery-section" aria-labelledby="discover-title"><div className="section-heading"><div><p className="eyebrow">Для вашего события</p><h2 id="discover-title">Кого вы ищете?</h2></div><Link className="intro-link" href="/search?kind=artist">Все артисты ↗</Link></div>
      <div className="discovery-links"><Link href="/search?kind=artist&category=dj">Диджей ↗</Link><Link href="/search?kind=artist&category=host">Ведущий ↗</Link><Link href="/search?kind=artist&category=cover">Кавер-группа ↗</Link></div>
    </section>
    <section className="home-process" aria-labelledby="process-title"><div className="section-heading"><div><p className="eyebrow">Как это работает</p><h2 id="process-title">Одна дата.<br />Общие договорённости.</h2></div></div>
      <div className="process-grid"><article><span className="process-number">01</span><h3>Найдите друг друга</h3><p>Заказчик выбирает артиста в каталоге. Артист находит подходящий открытый заказ или получает личную заявку.</p></article><article><span className="process-number">02</span><h3>Обсудите детали</h3><p>Дата, программа, райдер и стоимость — в одном предложении. Обе стороны видят, что нужно согласовать.</p></article><article><span className="process-number">03</span><h3>Подтвердите выступление</h3><p>Согласуйте условия и подтвердите договорённости. Заявка сама по себе ещё не бронирует дату.</p></article></div>
    </section>
    <section className="home-supply" aria-labelledby="supply-title"><div><p className="eyebrow">Вы артист?</p><h2 id="supply-title">Пусть вас найдут.</h2><p>Покажите свои выступления, укажите условия и свободные даты. Получайте заявки и ведите договорённости в своём кабинете.</p></div><Link className="btn" href="/login?mode=register&role=artist&next=%2Fcabinet%2Fperformer">Создать профиль артиста ↗</Link></section>
    <p className="legal-banner">Пилотный запуск: юридические документы дорабатываются, платежи на платформе отключены. <Link href="/legal">Правила сервиса</Link></p>
  </main>;
}
