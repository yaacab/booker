import { createHash } from "node:crypto";
import { readLegalFile } from "@/lib/legal";

export const dynamic = "force-dynamic";

const FILES = {
  offer: "OFFER_DRAFT.md",
  privacy: "PRIVACY_DRAFT.md",
  consent_texts: "CONSENT_TEXTS.md",
  cookies: "COOKIES_DRAFT.md",
  disputes: "DISPUTES_REFUNDS_DRAFT.md",
  suppliers: "SUPPLIER_TERMS_DRAFT.md",
  cancellation: "CANCELLATION_TARIFF.md",
} as const;

export async function GET() {
  try {
    const hashes = Object.fromEntries(await Promise.all(
      Object.entries(FILES).map(async ([key, file]) => [
        key, createHash("sha256").update(await readLegalFile(file)).digest("hex"),
      ]),
    ));
    return Response.json({ hashes }, { headers: { "Cache-Control": "no-store" } });
  } catch {
    return Response.json({ error: "visible legal text unavailable" }, { status: 503 });
  }
}
