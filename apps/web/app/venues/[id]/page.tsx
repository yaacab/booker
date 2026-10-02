import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { cache } from "react";
import {
  VenueProfileClient,
  type VenueProfileData,
} from "@/components/VenueProfileClient";

const API =
  process.env.BOOKER_INTERNAL_API_URL ||
  process.env.NEXT_PUBLIC_API_URL ||
  "http://127.0.0.1:8000";

const getVenue = cache(async (id: string): Promise<VenueProfileData | null> => {
  const res = await fetch(`${API}/venues/${encodeURIComponent(id)}`, {
    next: { revalidate: 300 },
  });
  if (res.status === 404) return null;
  if (!res.ok) throw new Error(`Venue profile API failed with ${res.status}`);
  return (await res.json()) as VenueProfileData;
});

export async function generateMetadata({
  params,
}: {
  params: Promise<{ id: string }>;
}): Promise<Metadata> {
  const { id } = await params;
  const data = await getVenue(id);
  if (!data) notFound();
  const title = `${data.name} — площадка · Букер`;
  const description = [data.name, data.city, data.address].filter(Boolean).join(" · ");
  return {
    title,
    description,
    alternates: { canonical: `/venues/${id}` },
    openGraph: {
      title,
      description,
      url: `/venues/${id}`,
      images: data.photos?.[0]?.url ? [data.photos[0].url] : undefined,
    },
  };
}

export default async function VenuePage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const venue = await getVenue(id);
  if (!venue) notFound();
  return <VenueProfileClient venueId={id} initialData={venue} />;
}
