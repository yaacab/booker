import { seoFetch, sitemapUnavailable, sitemapXml, type SeoIndex } from '@/lib/public-seo';
export const dynamic = 'force-dynamic';
export async function GET() {
  try {
    const data = await seoFetch<SeoIndex>('/index');
    if (!data) return sitemapUnavailable();
    const paths = ['/sitemaps/pages.xml'];
    for (const kind of ['artists', 'venues'] as const) {
      for (let page = 0; page < Math.ceil(data.counts[kind] / data.page_size); page++) paths.push(`/sitemaps/${kind}/${page}.xml`);
    }
    return sitemapXml(paths, true);
  } catch { return sitemapUnavailable(); }
}
