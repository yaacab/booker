import { LegalDoc } from "@/components/LegalDoc";
import { readLegalFile } from "@/lib/legal";

export const dynamic = "force-dynamic";
export const metadata = { title: "Cookie-файлы", alternates: { canonical: "/legal/cookies" } };

export default async function CookiesPage() {
  return <LegalDoc source={await readLegalFile("COOKIES_DRAFT.md")} />;
}
