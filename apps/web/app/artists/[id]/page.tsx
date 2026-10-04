import type { Metadata } from "next";
import { notFound } from "next/navigation";
import { cache } from "react";
import {
  ArtistProfileClient,
  type ArtistProfileData,
} from "@/components/ArtistProfileClient";

const API =
  process.env.BOOKER_INTERNAL_API_URL ||
  process.env.NEXT_PUBLIC_API_URL ||
  "http://127.0.0.1:8000";

const getArtist = cache(async (id: string): Promise<ArtistProfileData | null> => {
  const res = await fetch(`${API}/artists/${encodeURIComponent(id)}`, {
    next: { revalidate: 300 },
  });
  if (res.status === 404) return null;
  if (!res.ok) throw new Error(`Artist profile API failed with ${res.status}`);
  return (await res.json()) as ArtistProfileData;
});

export async function generateMetadata({
  params,
}: {
  params: Promise<{ id: string }>;
}): Promise<Metadata> {
  const { id } = await params;
  const data = await getArtist(id);
  if (!data) notFound();
  const title = `${data.name} — артист · Букер`;
  const description = [data.name, data.city, data.category].filter(Boolean).join(" · ");
  return {
    title,
    description,
    alternates: { canonical: `/artists/${id}` },
    openGraph: {
      title,
      description,
      url: `/artists/${id}`,
      images: data.media_url ? [data.media_url] : undefined,
    },
  };
}

export default async function ArtistPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  const artist = await getArtist(id);
  if (!artist) notFound();
  return <ArtistProfileClient artistId={id} initialData={artist} />;
}
