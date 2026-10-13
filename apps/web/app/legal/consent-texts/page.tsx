import { LegalDoc } from "@/components/LegalDoc";
import { readLegalFile } from "@/lib/legal";

export const dynamic = "force-dynamic";
export const metadata = { title: "Тексты согласий", alternates: { canonical: "/legal/consent-texts" } };

export default async function ConsentTextsPage() {
  return <LegalDoc source={await readLegalFile("CONSENT_TEXTS.md")} documentKey="consent_texts" />;
}
