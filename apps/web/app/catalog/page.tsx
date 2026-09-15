import type { Metadata } from 'next';
import Link from 'next/link';
import { CatalogLink } from '@/components/catalog/CatalogLink';
import { CANONICAL_ORIGIN, seoFetch, type SeoIndex } from '@/lib/public-seo';
export const dynamic = 'force-dynamic';
export async function generateMetadata(): Promise<Metadata> {
  try {
    const data = await seoFetch<SeoIndex>('/index');
    return { title: 'Исполнители и площадки по задачам', alternates: { canonical: `${CANONICAL_ORIGIN}/catalog` }, robots: { index: Boolean(data?.collections.length) } };
  } catch { return { title: 'Каталог', robots: { index: false } }; }
}
export default async function CatalogDirectory() {
  const data = await seoFetch<SeoIndex>('/index');
  return <main className="commerce-page"><p className="kicker">Люди и места</p><h1>С чего начнётся ваше событие?</h1>
    <p>Выберите задачу, посмотрите профили и сравните опубликованные условия. Дату, состав и итоговую стоимость участники согласуют в предложении.</p>
    {!data?.collections.length ? <p className="empty">Подборки ещё готовятся. Профили можно найти в общем поиске.</p> : <div className="public-catalog-grid">{data.collections.map(item => <article className="card" key={item.path}><h2><CatalogLink href={item.path}>{item.title}</CatalogLink></h2><p>{item.description}</p><p className="timeline">Профилей: {item.count}</p></article>)}</div>}
    <p><Link className="btn" href="/search">Поиск по дате и условиям</Link></p>
  </main>;
}
