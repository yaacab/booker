import { LegalDoc } from "@/components/LegalDoc";
import { readLegalFile } from "@/lib/legal";

export const dynamic = "force-dynamic";
export const metadata = { title: "Оферта", alternates: { canonical: "/legal/offer" } };

export default async function OfferPage() {
  return <LegalDoc source={await readLegalFile("OFFER_DRAFT.md")} />;
}
