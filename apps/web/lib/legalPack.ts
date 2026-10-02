import { api } from "./api";

export type LegalDocumentKey =
  | "offer" | "privacy" | "consent_texts" | "cookies"
  | "disputes" | "suppliers" | "cancellation";

export type LegalPackDocument = {
  key: LegalDocumentKey;
  version: string;
  content_hash: string;
  status: "draft" | "published" | "retired";
  required: boolean;
  href: string;
};

export type LegalPack = {
  pack_version: string | null;
  status: "draft" | "published" | "unavailable";
  registration_available: boolean;
  acceptance_effect: "test_acknowledgement" | "legal_acceptance" | "unavailable";
  documents: LegalPackDocument[];
  visible_source_match?: boolean;
};

export type AcceptedLegalDocument = Pick<LegalPackDocument, "key" | "version" | "content_hash">;

const REQUIRED_KEYS = ["offer", "privacy", "consent_texts"] as const;
const HASH = /^[0-9a-f]{64}$/;
const LEGAL_HREFS: Record<LegalDocumentKey, string> = {
  offer: "/legal/offer", privacy: "/legal/privacy", consent_texts: "/legal/consent-texts",
  cookies: "/legal/cookies", disputes: "/legal/disputes",
  suppliers: "/legal/suppliers", cancellation: "/legal/cancellation",
};

export function registrationLegalState(pack: LegalPack | null): {
  available: boolean;
  draftTest: boolean;
  accepted_documents: AcceptedLegalDocument[];
  required_documents: LegalPackDocument[];
} {
  const unavailable = { available: false, draftTest: false, accepted_documents: [], required_documents: [] };
  if (!pack || pack.registration_available !== true || pack.visible_source_match === false ||
      typeof pack.pack_version !== "string" ||
      !pack.pack_version || !Array.isArray(pack.documents) ||
      pack.documents.some((document) => !document || typeof document !== "object")) return unavailable;
  const documentKeys = pack.documents.map((document) => document.key);
  if (pack.documents.length !== ALL_KEYS.length || new Set(documentKeys).size !== ALL_KEYS.length ||
      ALL_KEYS.some((key) => !documentKeys.includes(key)) ||
      pack.documents.some((document) =>
        !ALL_KEYS.includes(document.key) ||
        typeof document.version !== "string" || document.version !== pack.pack_version ||
        typeof document.content_hash !== "string" || !HASH.test(document.content_hash) ||
        document.href !== LEGAL_HREFS[document.key] ||
        document.required !== REQUIRED_KEYS.includes(document.key as typeof REQUIRED_KEYS[number]))) {
    return unavailable;
  }
  const required = pack.documents.filter((document) => document.required)
    .sort((a, b) => REQUIRED_KEYS.indexOf(a.key as typeof REQUIRED_KEYS[number]) -
      REQUIRED_KEYS.indexOf(b.key as typeof REQUIRED_KEYS[number]));
  const keys = required.map((document) => document.key);
  if (required.length !== REQUIRED_KEYS.length || new Set(keys).size !== REQUIRED_KEYS.length ||
      REQUIRED_KEYS.some((key) => !keys.includes(key))) return unavailable;
  const draftTest = pack.status === "draft" && pack.acceptance_effect === "test_acknowledgement" &&
    pack.documents.every((document) => document.status === "draft");
  const published = pack.status === "published" && pack.acceptance_effect === "legal_acceptance" &&
    pack.documents.every((document) => document.status === "published");
  if (!draftTest && !published) return unavailable;
  return {
    available: true,
    draftTest,
    accepted_documents: required.map(({ key, version, content_hash }) => ({ key, version, content_hash })),
    required_documents: required,
  };
}

export function legalDocumentLabel(key: LegalDocumentKey): string {
  const labels: Record<LegalDocumentKey, string> = {
    offer: "Оферта", privacy: "Персональные данные", consent_texts: "Тексты согласий",
    cookies: "Cookie-файлы", disputes: "Споры и возвраты",
    suppliers: "Исполнители и площадки", cancellation: "Отмены",
  };
  return labels[key];
}

export function legalDocumentHref(key: LegalDocumentKey): string {
  return LEGAL_HREFS[key];
}

const ALL_KEYS: LegalDocumentKey[] = ["offer", "privacy", "consent_texts", "cookies", "disputes", "suppliers", "cancellation"];

export function visiblePackDocumentsMatch(pack: LegalPack, hashes: Record<string, string>): boolean {
  if (pack.documents.length !== ALL_KEYS.length || new Set(pack.documents.map((item) => item.key)).size !== ALL_KEYS.length) {
    return false;
  }
  return ALL_KEYS.every((key) => {
    const document = pack.documents.find((item) => item.key === key);
    return !!document && document.content_hash === hashes[key];
  });
}

export async function getPublicLegalPack(): Promise<LegalPack | null> {
  try {
    const pack = await api<LegalPack>("/legal/pack", { cache: "no-store" });
    if (typeof window !== "undefined" && pack.registration_available) {
      const response = await fetch("/api/legal/visible-hashes", { cache: "no-store" });
      if (!response.ok) return { ...pack, registration_available: false, visible_source_match: false };
      const visible = await response.json() as { hashes?: Record<string, string> };
      if (!visible.hashes || !visiblePackDocumentsMatch(pack, visible.hashes)) {
        return { ...pack, registration_available: false, visible_source_match: false };
      }
      return { ...pack, visible_source_match: true };
    }
    return pack;
  } catch {
    return null;
  }
}
