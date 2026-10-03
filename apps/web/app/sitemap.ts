import type { MetadataRoute } from "next";
import {
  INDEXABLE_STATIC_PATHS,
  canonicalSiteUrl,
  publicProfilePath,
} from "@/lib/seo";

const API =
  process.env.BOOKER_INTERNAL_API_URL ||
  process.env.NEXT_PUBLIC_API_URL ||
  "http://127.0.0.1:8000";

type PublicIndexPage = {
  items?: { type: "artist" | "venue"; id: string }[];
  next_cursor?: string | null;
};

export const revalidate = 3600;
export const dynamic = "force-dynamic";

async function loadAllPublicProfiles(): Promise<NonNullable<PublicIndexPage["items"]>> {
  const items: NonNullable<PublicIndexPage["items"]> = [];
  const seenCursors = new Set<string>();
  let cursor: string | null = null;
  do {
    const query = new URLSearchParams({ limit: "200" });
    if (cursor) query.set("cursor", cursor);
    const res = await fetch(`${API}/catalog/public-index?${query}`, {
      cache: "no-store",
    });
    if (!res.ok) throw new Error(`Public catalog index failed with ${res.status}`);
    const page = (await res.json()) as PublicIndexPage;
    items.push(...(page.items || []));
    cursor = page.next_cursor || null;
    if (cursor && seenCursors.has(cursor)) throw new Error("Public catalog index cursor loop");
    if (cursor) seenCursors.add(cursor);
  } while (cursor);
  return items;
}

export default async function sitemap(): Promise<MetadataRoute.Sitemap> {
  const base = canonicalSiteUrl();
  const staticEntries: MetadataRoute.Sitemap = INDEXABLE_STATIC_PATHS.map((path) => ({
    url: `${base}${path === "/" ? "" : path}`,
    changeFrequency: path === "/search" ? "daily" : path === "/" ? "weekly" : "monthly",
    priority: path === "/" ? 1 : path === "/search" ? 0.8 : 0.4,
  }));
  const seen = new Set<string>();
  const profileEntries: MetadataRoute.Sitemap = [];
  for (const profile of await loadAllPublicProfiles()) {
    const path = publicProfilePath(profile.type, profile.id);
    if (seen.has(path)) continue;
    seen.add(path);
    profileEntries.push({
      url: `${base}${path}`,
      changeFrequency: "weekly",
      priority: profile.type === "artist" ? 0.6 : 0.5,
    });
  }
  return [...staticEntries, ...profileEntries];
}
