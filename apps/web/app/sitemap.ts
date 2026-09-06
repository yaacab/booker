import type { MetadataRoute } from "next";

const API =
  process.env.BOOKER_INTERNAL_API_URL ||
  process.env.NEXT_PUBLIC_API_URL ||
  "http://127.0.0.1:8000";

export default async function sitemap(): Promise<MetadataRoute.Sitemap> {
  const base = process.env.NEXT_PUBLIC_SITE_URL || "https://bukergo.ru";
  const staticEntries: MetadataRoute.Sitemap = [
    { url: base, changeFrequency: "weekly", priority: 1 },
    { url: `${base}/search`, changeFrequency: "daily", priority: 0.8 },
    { url: `${base}/events/new`, changeFrequency: "weekly", priority: 0.7 },
    { url: `${base}/faq`, changeFrequency: "monthly", priority: 0.4 },
    { url: `${base}/login`, changeFrequency: "monthly", priority: 0.4 },
    { url: `${base}/legal`, changeFrequency: "monthly", priority: 0.4 },
    { url: `${base}/legal/offer`, changeFrequency: "monthly", priority: 0.3 },
    { url: `${base}/legal/privacy`, changeFrequency: "monthly", priority: 0.3 },
    { url: `${base}/legal/disputes`, changeFrequency: "monthly", priority: 0.3 },
    { url: `${base}/legal/cookies`, changeFrequency: "monthly", priority: 0.2 },
    { url: `${base}/legal/suppliers`, changeFrequency: "monthly", priority: 0.2 },
    { url: `${base}/legal/cancellation`, changeFrequency: "monthly", priority: 0.2 },
  ];

  const profileEntries: MetadataRoute.Sitemap = [];
  try {
    const res = await fetch(`${API}/catalog/search?city=${encodeURIComponent("Москва")}`, {
      next: { revalidate: 3600 },
    });
    if (res.ok) {
      const data = (await res.json()) as {
        items?: { id: string }[];
        venues?: { id: string }[];
      };
      for (const a of data.items || []) {
        profileEntries.push({
          url: `${base}/artists/${a.id}`,
          changeFrequency: "weekly",
          priority: 0.6,
        });
      }
      for (const v of (data.venues || []).slice(0, 200)) {
        profileEntries.push({
          url: `${base}/venues/${v.id}`,
          changeFrequency: "weekly",
          priority: 0.5,
        });
      }
    }
  } catch {
    // sitemap still returns static pages if API is down
  }

  return [...staticEntries, ...profileEntries];
}
