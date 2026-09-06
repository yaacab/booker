import type { Metadata } from "next";
import { VenueProfileClient } from "@/components/VenueProfileClient";

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
    const res = await fetch(`${API}/venues/${id}`, { next: { revalidate: 300 } });
    if (!res.ok) return { title: "Площадка · Букер", robots: { index: false } };
    const data = (await res.json()) as { name?: string; city?: string; address?: string };
    const title = data.name ? `${data.name} — площадка · Букер` : "Площадка · Букер";
    const description = [data.name, data.city, data.address].filter(Boolean).join(" · ");
    return {
      title,
      description,
      alternates: { canonical: `/venues/${id}` },
      openGraph: { title, description, url: `/venues/${id}` },
    };
  } catch {
    return { title: "Площадка · Букер" };
  }
}

export default function VenuePage({ params }: { params: Promise<{ id: string }> }) {
  return <VenueProfileClient params={params} />;
}
