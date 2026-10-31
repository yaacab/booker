import { LegalDoc } from "@/components/LegalDoc";
import { readLegalFile } from "@/lib/legal";

export const dynamic = "force-dynamic";
export const metadata = { title: "Споры", alternates: { canonical: "/legal/disputes" } };

export default async function DisputesPage() {
  return <LegalDoc source={await readLegalFile("DISPUTES_REFUNDS_DRAFT.md")} />;
}
