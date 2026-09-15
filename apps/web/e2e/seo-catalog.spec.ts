import { expect, test } from '@playwright/test';
import { API_BASE, postJson, register } from './helpers';

for (const width of [1440, 390]) {
  test(`Public collection renders HTML, metadata and useful facts at ${width}px`, async ({ page }, testInfo) => {
    await page.setViewportSize({ width, height: 900 });
    await page.goto('/catalog/moskva/dj');
    await expect(page.getByRole('heading', { name: 'DJ в Москве', exact: true })).toBeVisible();
    await expect(page).toHaveTitle('DJ в Москве · Букер');
    await expect(page.locator('link[rel="canonical"]')).toHaveAttribute('href', 'https://bukergo.ru/catalog/moskva/dj');
    await expect(page.locator('meta[property="og:title"]')).toHaveAttribute('content', 'DJ в Москве');
    const cards = page.locator('.public-catalog-grid article');
    expect(await cards.count()).toBeGreaterThanOrEqual(3);
    await expect(page.getByText('Цены в подборке — ориентиры.', { exact: false })).toBeVisible();
    const link = cards.first().getByRole('link');
    await link.focus(); await expect(link).toBeFocused();
    const structured = JSON.parse((await page.locator('script[type="application/ld+json"]').textContent())!);
    expect(structured['@type']).toBe('ItemList');
    expect(structured.itemListElement.length).toBe(await cards.count());
    expect(JSON.stringify(structured)).not.toContain('aggregateRating');
    expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
    await page.evaluate(() => scrollTo(0, 0));
    await page.screenshot({ path: testInfo.outputPath('catalog-collection.png') });
  });
}

test('Collection is readable without JavaScript and sparse routes return 404', async ({ browser, request }) => {
  const context = await browser.newContext({ javaScriptEnabled: false, baseURL: process.env.BOOKER_WEB_URL || 'http://127.0.0.1:3000' });
  const page = await context.newPage();
  await page.goto('/catalog/moskva/dj');
  await expect(page.getByRole('heading', { name: 'DJ в Москве', exact: true })).toBeVisible();
  expect(await page.locator('.public-catalog-grid article').count()).toBeGreaterThanOrEqual(3);
  await context.close();
  expect((await request.get('/catalog/unknown/dj')).status()).toBe(404);
  expect((await request.get('/catalog/moskva/nonexistent')).status()).toBe(404);
});

test('Sitemap covers public profiles beyond Moscow and omits private flows', async ({ request }) => {
  const user = await register(request, `seo-${Date.now()}@booker.test`, 'Публичный профиль');
  const org = await postJson<{ id: string }>(request, '/orgs', user.token, { name: 'Студия', kind: 'artist' });
  const artist = await postJson<{ id: string }>(request, '/artists', user.token, { organization_id: org.id, name: 'Артист без календаря', city: 'Казань', category: 'dj' });
  const sitemap = await request.get('/sitemap.xml');
  expect(sitemap.ok()).toBe(true);
  const xml = await sitemap.text();
  expect(xml).toContain('<sitemapindex');
  const locations = [...xml.matchAll(/<loc>(.*?)<\/loc>/g)].map(match => match[1]);
  let found = false;
  for (const location of locations.filter(value => value.includes('/sitemaps/artists/'))) {
    expect(location.startsWith('https://bukergo.ru/sitemaps/')).toBe(true);
    const child = await request.get(location.replace('https://bukergo.ru', ''));
    expect(child.ok()).toBe(true);
    if ((await child.text()).includes(`/artists/${artist.id}</loc>`)) found = true;
  }
  expect(found).toBe(true);
  const pages = await (await request.get('/sitemaps/pages.xml')).text();
  expect(pages).toContain('https://bukergo.ru/pricing');
  expect(pages).not.toContain('/login');
  expect(pages).not.toContain('/events/new');
  const profile = await request.get(`/artists/${artist.id}`);
  expect(await profile.text()).toContain(`https://bukergo.ru/artists/${artist.id}`);
  expect((await request.get('/sitemaps/unknown/0.xml')).status()).toBe(404);
  const robots = await (await request.get('/robots.txt')).text();
  expect(robots).toContain('Disallow: /cabinet');
  expect(robots).not.toContain('User-Agent: GPTBot');
  const inventory = await request.get(`${API_BASE}/seo/index`);
  expect(inventory.ok()).toBe(true);
});

test('Directory keyboard navigation shows loading while a collection is requested', async ({ page }) => {
  let release!: () => void;
  const pending = new Promise<void>(resolve => { release = resolve; });
  await page.route('**/catalog/moskva/dj?*', async route => { await pending; await route.continue(); });
  await page.goto('/catalog');
  const link = page.getByRole('link', { name: 'DJ в Москве', exact: true });
  await link.focus();
  await link.press('Enter');
  try { await expect(page.getByRole('status').filter({ hasText: 'Загружаем' })).toBeVisible(); }
  finally { release(); }
  await expect(page.getByRole('heading', { name: 'DJ в Москве', exact: true })).toBeVisible();
});
