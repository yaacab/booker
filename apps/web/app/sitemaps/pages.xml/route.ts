import { PUBLIC_PATHS, seoFetch, sitemapUnavailable, sitemapXml, type SeoIndex } from '@/lib/public-seo';
export const dynamic = 'force-dynamic';
export async function GET() {
  try {
    const data = await seoFetch<SeoIndex>('/index');
    if (!data) return sitemapUnavailable();
    return sitemapXml([...PUBLIC_PATHS.filter(path => path !== '/catalog' || data.collections.length > 0), ...data.collections.map(item => item.path)]);
  } catch { return sitemapUnavailable(); }
}
