import type { Metadata } from "next";
import { categoryLabel } from "@/lib/copy";
import { ArtistProfileClient } from "@/components/ArtistProfileClient";

const API =
  process.env.BOOKER_INTERNAL_API_URL ||
  process.env.NEXT_PUBLIC_API_URL ||
  "http://127.0.0.1:8000";

export async function generateMetadata({
  params,
}: {
  params: Promise<{ id: string }>;
}): Promise<Metadata> {
  const { id } = await params;
  try {
    const res = await fetch(`${API}/artists/${id}`, { next: { revalidate: 300 } });
    if (!res.ok) return { title: "Артист", robots: { index: false } };
    const data = (await res.json()) as { name?: string; city?: string; category?: string; presentation?: { format?: string; cover_url?: string } };
    const title = data.name ? `${data.name} — артист` : "Артист";
    const description = [data.name, data.city, categoryLabel(data.category || ""), data.presentation?.format].filter(Boolean).join(" · ");
    return {
      title,
      description,
      alternates: { canonical: `/artists/${id}` },
      openGraph: { title, description, url: `/artists/${id}`, images: data.presentation?.cover_url ? [data.presentation.cover_url] : undefined },
    };
  } catch {
    return { title: "Артист", robots: { index: false } };
  }
}

export default function ArtistPage() {
  return <ArtistProfileClient />;
}
