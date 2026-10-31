import { LegalDoc } from "@/components/LegalDoc";
import { readLegalFile } from "@/lib/legal";

export const dynamic = "force-dynamic";
export const metadata = { title: "Исполнители", alternates: { canonical: "/legal/suppliers" } };

export default async function SuppliersPage() {
  return <LegalDoc source={await readLegalFile("SUPPLIER_TERMS_DRAFT.md")} />;
}
