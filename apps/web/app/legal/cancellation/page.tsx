import { LegalDoc } from "@/components/LegalDoc";
import { readLegalFile } from "@/lib/legal";

export const dynamic = "force-dynamic";
export const metadata = { title: "Отмены", alternates: { canonical: "/legal/cancellation" } };

export default async function CancellationPage() {
  return <LegalDoc source={await readLegalFile("CANCELLATION_TARIFF.md")} />;
}
