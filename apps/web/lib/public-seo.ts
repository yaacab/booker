export const CANONICAL_ORIGIN = 'https://bukergo.ru';
export const PUBLIC_PATHS = ['/', '/search', '/catalog', '/pricing', '/faq', '/legal', '/legal/offer', '/legal/privacy', '/legal/disputes', '/legal/cookies', '/legal/suppliers', '/legal/cancellation'];
const API = process.env.BOOKER_INTERNAL_API_URL || process.env.NEXT_PUBLIC_API_URL || 'http://127.0.0.1:8000';
export type Collection = { path: string; city_slug: string; city: string; category: string; title: string; description: string; count: number };
export type SeoIndex = { page_size: number; counts: { artists: number; venues: number }; collections: Collection[] };
export type CollectionPage = Collection & { page: number; has_more: boolean; items: { id: string; kind: 'artist' | 'venue'; path: string; name: string; city: string; detail: string; honorarium_from_rub: number | null; availability_note: string }[] };
export type PublicVenueMetadataFacts = { name?: string; city?: string; address?: string };
export async function seoFetch<T>(path: string): Promise<T | null> {
  const response = await fetch(`${API}/seo${path}`, { cache: 'no-store', signal: AbortSignal.timeout(5000) });
  if (response.status === 404) return null;
  if (!response.ok) throw new Error('Public catalog is temporarily unavailable');
  return response.json() as Promise<T>;
}
export async function fetchPublicVenueMetadataFacts(id: string): Promise<PublicVenueMetadataFacts | null> {
  const response = await fetch(`${API}/venues/${encodeURIComponent(id)}`, { cache: 'no-store', signal: AbortSignal.timeout(5000) });
  if (!response.ok) return null;
  return response.json() as Promise<PublicVenueMetadataFacts>;
}
function xmlEscape(value: string) {
  return value.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;').replace(/'/g, '&apos;');
}
export function sitemapXml(paths: string[], index = false) {
  const root = index ? 'sitemapindex' : 'urlset';
  const item = index ? 'sitemap' : 'url';
  const body = `<?xml version="1.0" encoding="UTF-8"?><${root} xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">${paths.map(path => `<${item}><loc>${xmlEscape(CANONICAL_ORIGIN + path)}</loc></${item}>`).join('')}</${root}>`;
  const hasVenueInventory = paths.some(path => /(?:^|\/)venues(?:\/|$)/.test(path));
  const cacheControl = hasVenueInventory ? 'no-store, max-age=0' : 'public, max-age=300';
  return new Response(body, { headers: { 'Content-Type': 'application/xml; charset=utf-8', 'Cache-Control': cacheControl } });
}
export function sitemapUnavailable() {
  return new Response('Sitemap temporarily unavailable', { status: 503, headers: { 'Retry-After': '60', 'Cache-Control': 'no-store, max-age=0' } });
}
