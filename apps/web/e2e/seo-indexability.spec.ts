import { expect, test } from "@playwright/test";

const API_URL = process.env.BOOKER_API_URL ?? "http://127.0.0.1:8000";

type PublicProfile = { type: "artist" | "venue"; id: string };

test("sitemap exposes only published profiles and server HTML is indexable", async ({ request }) => {
  const indexResponse = await request.get(`${API_URL}/catalog/public-index?limit=200`);
  expect(indexResponse.ok()).toBeTruthy();
  const index = (await indexResponse.json()) as { items: PublicProfile[] };
  expect(index.items.length).toBeGreaterThanOrEqual(2);

  const sitemapResponse = await request.get("/sitemap.xml");
  expect(sitemapResponse.status()).toBe(200);
  const sitemap = await sitemapResponse.text();
  expect(sitemap).toContain("https://bukergo.ru/search");
  expect(sitemap).not.toContain("/login");
  expect(sitemap).not.toContain("/events/new");
  expect(sitemap).not.toContain("/investor/");

  for (const profile of index.items) {
    const segment = profile.type === "artist" ? "artists" : "venues";
    const path = `/${segment}/${profile.id}`;
    expect(sitemap).toContain(`https://bukergo.ru${path}`);

    const apiResponse = await request.get(`${API_URL}/${segment}/${profile.id}`);
    expect(apiResponse.ok()).toBeTruthy();
    const apiProfile = (await apiResponse.json()) as { name: string };

    const profileResponse = await request.get(path);
    expect(profileResponse.status()).toBe(200);
    const html = await profileResponse.text();
    expect(html).toContain(apiProfile.name);
    expect(html).toContain(`<h1>${apiProfile.name}</h1>`);
    expect(html).toContain(`rel="canonical" href="https://bukergo.ru${path}"`);
    expect(html).not.toContain('name="robots" content="noindex');
  }
});

test("unknown profiles return HTTP 404 and private routes carry noindex", async ({ page, request }) => {
  expect((await page.goto("/artists/unknown-profile"))?.status()).toBe(404);
  expect((await page.goto("/venues/unknown-profile"))?.status()).toBe(404);

  for (const path of ["/login", "/events/new", "/support", "/compare", "/briefs"]) {
    const response = await request.get(path);
    expect(response.status()).toBe(200);
    expect(await response.text()).toContain('name="robots" content="noindex, nofollow"');
  }
});
