import type { Metadata } from 'next';
import Link from 'next/link';
import { CatalogLink } from '@/components/catalog/CatalogLink';
import { notFound } from 'next/navigation';
import { PublicCatalogCard } from '@/components/catalog/PublicCatalogCard';
import { money } from '@/lib/format';
import { CANONICAL_ORIGIN, seoFetch, type CollectionPage } from '@/lib/public-seo';
export const dynamic = 'force-dynamic';
type Props = { params: Promise<{ city: string; category: string }>; searchParams: Promise<{ page?: string }> };
async function load({ params, searchParams }: Props) {
  const { city, category } = await params;
  const query = await searchParams;
  if (query.page && (!/^[1-9]\d{0,4}$/.test(query.page) || Number(query.page) > 10001)) return null;
  const page = Number(query.page || '1');
  return seoFetch<CollectionPage>(`/collections/${encodeURIComponent(city)}/${encodeURIComponent(category)}?page=${page - 1}`);
}
export async function generateMetadata(props: Props): Promise<Metadata> {
  try {
    const data = await load(props);
    if (!data) return { title: 'Подборка не найдена', robots: { index: false } };
    const url = `${CANONICAL_ORIGIN}${data.path}${data.page ? `?page=${data.page + 1}` : ''}`;
    return { title: data.title + (data.page ? ` — страница ${data.page + 1}` : ''), description: data.description, alternates: { canonical: url }, openGraph: { title: data.title, description: data.description, url } };
  } catch { return { title: 'Подборка временно недоступна', robots: { index: false } }; }
}
export default async function PublicCollection(props: Props) {
  const data = await load(props);
  if (!data) notFound();
  const structured = { '@context': 'https://schema.org', '@type': 'ItemList', itemListElement: data.items.map((item, index) => ({ '@type': 'ListItem', position: data.page * 24 + index + 1, name: item.name, url: CANONICAL_ORIGIN + item.path })) };
  const search = `/search?city=${encodeURIComponent(data.city)}&category=${data.category === 'venues' ? 'venue' : data.category}`;
  return <main className="commerce-page"><nav aria-label="Навигация по каталогу"><Link href="/catalog">Все подборки</Link></nav>
    <header><p className="kicker">Профили и опубликованные условия</p><h1>{data.title}</h1><p>{data.description}</p><Link className="btn" href={search}>Проверить дату и условия</Link></header>
    <p className="timeline">Профили расположены по названию. Наличие в подборке не подтверждает свободную дату.</p>
    <div className="public-catalog-grid">{data.items.map(item => <PublicCatalogCard key={item.path} id={item.id} kind={item.kind}><p className="kicker">{item.city}</p><h2>{item.name}</h2>{item.detail && <p>{item.detail}</p>}
      <p>{item.honorarium_from_rub === null ? 'Условия — после запроса' : `Опубликованный ориентир: от ${money(item.honorarium_from_rub)}`}</p><p className="timeline">{item.availability_note}</p><Link className="btn secondary" href={item.path} aria-label={`${item.name} — открыть профиль`}>Открыть профиль</Link></PublicCatalogCard>)}</div>
    <nav className="commerce-actions" aria-label="Страницы подборки">{data.page > 0 && <CatalogLink href={data.page === 1 ? data.path : `${data.path}?page=${data.page}`}>Предыдущая страница</CatalogLink>}{data.has_more && <CatalogLink href={`${data.path}?page=${data.page + 2}`}>Следующая страница</CatalogLink>}</nav>
    <section><h2>От знакомства к предложению</h2><p>Откройте профиль, изучите портфолио и опубликованные тарифы. Затем уточните дату, длительность, состав услуг и требования площадки.</p><p>Цены в подборке — ориентиры. Итоговая стоимость и условия фиксируются в предложении участника, а доступность подтверждается для конкретной даты.</p><Link href="/events/new">Собрать заявку на событие</Link></section>
    <script type="application/ld+json" dangerouslySetInnerHTML={{ __html: JSON.stringify(structured).replace(/</g, '\\u003c') }} />
  </main>;
}
