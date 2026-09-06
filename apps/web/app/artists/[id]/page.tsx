import type { Metadata } from "next";
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
    if (!res.ok) return { title: "Артист · Букер", robots: { index: false } };
    const data = (await res.json()) as { name?: string; city?: string; category?: string };
    const title = data.name ? `${data.name} — артист · Букер` : "Артист · Букер";
    const description = [data.name, data.city, data.category].filter(Boolean).join(" · ");
    return {
      title,
      description,
      alternates: { canonical: `/artists/${id}` },
      openGraph: { title, description, url: `/artists/${id}` },
    };
  } catch {
    return { title: "Артист · Букер" };
  }
}

export default function ArtistPage() {
  return <ArtistProfileClient />;
}
