import { seoFetch, sitemapUnavailable, sitemapXml } from '@/lib/public-seo';
export const dynamic = 'force-dynamic';
export async function GET(_request: Request, { params }: { params: Promise<{ kind: string; page: string }> }) {
  const { kind, page } = await params;
  if (!['artists', 'venues'].includes(kind) || !/^(0|[1-9]\d{0,4})\.xml$/.test(page) || Number(page.slice(0, -4)) > 50000) return new Response('Not found', { status: 404 });
  try {
    const data = await seoFetch<{ items: { path: string }[] }>(`/profiles?kind=${kind}&page=${page.slice(0, -4)}`);
    if (!data) return sitemapUnavailable();
    if (!data.items.length) return new Response('Not found', { status: 404 });
    return sitemapXml(data.items.map(item => item.path));
  } catch { return sitemapUnavailable(); }
}
