import { registrationLegalState, type AcceptedLegalDocument, type LegalPack } from "./legalPack";

export type ConsentSession = { token: string | null; epoch: number };

export function createConsentSessionGuard(readToken: () => string | null) {
  let token = readToken();
  let epoch = 0;
  return {
    capture: (): ConsentSession => ({ token, epoch }),
    sync: () => {
      const next = readToken();
      if (next === token) return false;
      token = next;
      epoch += 1;
      return true;
    },
    invalidate: () => { epoch += 1; },
    isCurrent: (session: ConsentSession) => session.epoch === epoch &&
      session.token === token && session.token === readToken(),
  };
}

export type ConsentEvent = {
  id: string;
  kind: string;
  document_version: string;
  document_hash: string;
  action: string;
  channel: string;
  created_at: string;
  acceptance_effect?: "test_acknowledgement" | "legal_acceptance" | null;
};

export type ConsentHistory = {
  marketing_email_active: boolean;
  marketing_test_selected?: boolean;
  history: ConsentEvent[];
  legacy_evidence_status?: "legacy_unknown" | null;
};

const KIND_BY_KEY: Record<"offer" | "privacy" | "consent_texts", string> = {
  offer: "offer", privacy: "privacy", consent_texts: "processing",
};

export function consentReacceptState(pack: LegalPack | null, history: ConsentHistory | null): {
  available: boolean;
  accepted_documents: AcceptedLegalDocument[];
} {
  // Existing account consent does not depend on whether new registration is open.
  const legal = registrationLegalState(pack ? { ...pack, registration_available: true } : null);
  if (!history || !legal.available || legal.draftTest || pack?.visible_source_match === false ||
      pack?.status !== "published" ||
      pack.acceptance_effect !== "legal_acceptance") {
    return { available: false, accepted_documents: [] };
  }
  const current = legal.accepted_documents.every((document) => {
    const kind = KIND_BY_KEY[document.key as keyof typeof KIND_BY_KEY];
    const latest = [...history.history].reverse().find((event) => event.kind === kind && event.action === "accepted");
    return latest?.document_version === document.version && latest.document_hash === document.content_hash &&
      latest.acceptance_effect === "legal_acceptance";
  });
  return { available: !current, accepted_documents: current ? [] : legal.accepted_documents };
}

export function consentKindLabel(kind: string): string {
  const labels: Record<string, string> = {
    offer: "Оферта", privacy: "Персональные данные", processing: "Тексты согласий",
    marketing_email: "Рассылка",
  };
  return labels[kind] || "Другое согласие";
}

export function consentActionLabel(action: string): string {
  if (action === "accepted") return "Отмечено";
  if (action === "withdrawn") return "Отозвано";
  return "Действие зарегистрировано";
}
