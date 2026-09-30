import type { Metadata } from "next";
import { VenueProfileClient } from "@/components/VenueProfileClient";
import { fetchPublicVenueMetadataFacts } from "@/lib/public-seo";

export const dynamic = "force-dynamic";

export async function generateMetadata({
  params,
}: {
  params: Promise<{ id: string }>;
}): Promise<Metadata> {
  const { id } = await params;
  try {
    const data = await fetchPublicVenueMetadataFacts(id);
    if (!data) return { title: "Площадка", robots: { index: false } };
    const title = data.name ? `${data.name} — площадка` : "Площадка";
    const description = [data.name, data.city, data.address].filter(Boolean).join(" · ");
    return {
      title,
      description,
      alternates: { canonical: `/venues/${id}` },
      openGraph: { title, description, url: `/venues/${id}` },
    };
  } catch {
    return { title: "Площадка", robots: { index: false } };
  }
}

export default function VenuePage({ params }: { params: Promise<{ id: string }> }) {
  return <VenueProfileClient params={params} />;
}
