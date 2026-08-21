import type { MetadataRoute } from "next";

export default function sitemap(): MetadataRoute.Sitemap {
  const base = process.env.NEXT_PUBLIC_SITE_URL || "https://bukergo.ru";
  return [
    { url: base, changeFrequency: "weekly", priority: 1 },
    { url: `${base}/search`, changeFrequency: "daily", priority: 0.8 },
    { url: `${base}/events/new`, changeFrequency: "weekly", priority: 0.7 },
    { url: `${base}/deals/demo`, changeFrequency: "weekly", priority: 0.6 },
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
}
