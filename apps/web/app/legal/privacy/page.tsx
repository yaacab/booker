import { LegalDoc } from "@/components/LegalDoc";
import { readLegalFile } from "@/lib/legal";

export const dynamic = "force-dynamic";
export const metadata = { title: "Персональные данные", alternates: { canonical: "/legal/privacy" } };

export default async function PrivacyPage() {
  return <LegalDoc source={await readLegalFile("PRIVACY_DRAFT.md")} />;
}
