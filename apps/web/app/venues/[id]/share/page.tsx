import type { Metadata } from "next";
import { PromoSharePanel } from "@/components/promo/PromoSharePanel";

export async function generateMetadata({
  params,
}: {
  params: Promise<{ id: string }>;
}): Promise<Metadata> {
  const { id } = await params;
  return {
    title: "Поделиться профилем · Букер",
    robots: { index: false, follow: false },
    alternates: { canonical: `/venues/${id}/share` },
  };
}

type PageProps = {
  params: Promise<{ id: string }>;
  searchParams: Promise<{ hall?: string; tariff?: string }>;
};

export default async function VenueSharePage({ params, searchParams }: PageProps) {
  const { id } = await params;
  const query = await searchParams;
  return (
    <PromoSharePanel kind="venue" profileId={id} hallId={query.hall} tariffId={query.tariff} />
  );
}
