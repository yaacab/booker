import Link from "next/link";
import ArtistFirstHero from "@/components/ArtistFirstHero";
export const metadata = { alternates: { canonical: "/" } };
export default function HomePage() {
  return <main className="page-enter immersive-home artist-first-home home-refined">
    <script type="application/ld+json" dangerouslySetInnerHTML={{__html:JSON.stringify({"@context":"https://schema.org","@graph":[{"@type":"Organization",name:"Букер",url:"https://bukergo.ru",email:"hello@bukergo.ru",description:"Сервис поиска артистов и работы для артистов. Согласование условий и сопровождение сделки."},{"@type":"WebSite",name:"Букер",url:"https://bukergo.ru",inLanguage:"ru"}]})}}/>
    <ArtistFirstHero />
    <section className="discovery-section" aria-labelledby="discover-title"><div className="section-heading"><div><p className="eyebrow">Для вашего события</p><h2 id="discover-title">Кого вы ищете?</h2></div><Link className="intro-link" href="/search?kind=artist">Все артисты ↗</Link></div>
      <div className="discovery-links">
        <Link href="/search?kind=artist&category=dj"><span className="category-art category-dj" aria-hidden="true"><i/><i/><i/><i/><i/><i/><i/></span><span className="category-copy"><strong>Диджей</strong><small>Ритм вашего вечера</small></span><span className="category-arrow" aria-hidden="true">↗</span></Link>
        <Link href="/search?kind=artist&category=host"><span className="category-art category-host" aria-hidden="true"><svg viewBox="0 0 80 80" fill="none" stroke="currentColor" strokeWidth="3"><rect x="31" y="12" width="18" height="35" rx="9"/><path d="M23 36v5a17 17 0 0 0 34 0v-5M40 58v13M28 71h24"/></svg></span><span className="category-copy"><strong>Ведущий</strong><small>Лёгкость в каждом моменте</small></span><span className="category-arrow" aria-hidden="true">↗</span></Link>
        <Link href="/search?kind=artist&category=cover"><span className="category-art category-cover" aria-hidden="true"><svg viewBox="0 0 80 80" fill="none" stroke="currentColor" strokeWidth="3"><path d="M30 58V23l34-7v34M30 32l34-7"/><ellipse cx="21" cy="58" rx="9" ry="7"/><ellipse cx="55" cy="50" rx="9" ry="7"/></svg></span><span className="category-copy"><strong>Кавер-группа</strong><small>Любимые песни вживую</small></span><span className="category-arrow" aria-hidden="true">↗</span></Link>
      </div>
    </section>
    <section className="home-process" aria-labelledby="process-title"><div className="section-heading"><div><p className="eyebrow">Как это работает</p><h2 id="process-title">От знакомства<br />до выступления.</h2></div></div>
      <div className="process-grid"><article><span className="process-number">01</span><h3>Найдите друг друга</h3><p>Выберите артиста или подходящее событие. Расскажите, что хотите организовать.</p></article><article><span className="process-number">02</span><h3>Обсудите детали</h3><p>Обсудите дату, программу и стоимость в общей переписке. Сохраните согласованные условия.</p></article><article><span className="process-number">03</span><h3>Подтвердите выступление</h3><p>Подтвердите условия с другой стороной. До этого момента заявка не бронирует дату.</p></article></div>
    </section>
    <section className="home-supply" aria-labelledby="supply-title"><div><p className="eyebrow">Вы артист?</p><h2 id="supply-title">Пусть вас найдут.</h2><p>Покажите свои выступления, укажите условия и свободные даты. Получайте заявки и ведите договорённости в своём кабинете.</p></div><Link className="btn" href="/login?mode=register&role=artist&next=%2Fcabinet%2Fperformer">Создать профиль артиста ↗</Link></section>
    <p className="legal-banner">Пилотный запуск: юридические документы дорабатываются, платежи на платформе отключены. <Link href="/legal">Правила сервиса</Link></p>
  </main>;
}
