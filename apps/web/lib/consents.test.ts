import test from "node:test";
import assert from "node:assert/strict";
import { consentReacceptState, createConsentSessionGuard, type ConsentHistory } from "./consents";
import type { LegalPack } from "./legalPack";

const keys = ["offer", "privacy", "consent_texts"] as const;
const allKeys = [...keys, "cookies", "disputes", "suppliers", "cancellation"] as const;
const hash = "a".repeat(64);

function pack(status: "draft" | "published" = "published"): LegalPack {
  return {
    pack_version: "v2", status, registration_available: false,
    acceptance_effect: status === "draft" ? "test_acknowledgement" : "legal_acceptance",
    documents: allKeys.map((key) => ({ key, version: "v2", content_hash: hash,
      status, required: keys.includes(key as typeof keys[number]),
      href: key === "consent_texts" ? "/legal/consent-texts" : `/legal/${key}` })),
  };
}

function history(version = "v1"): ConsentHistory {
  return {
    marketing_email_active: false,
    legacy_evidence_status: "legacy_unknown",
    history: keys.map((key, index) => ({
      id: String(index), kind: key === "consent_texts" ? "processing" : key,
      document_version: version, document_hash: hash, action: "accepted",
      channel: "web", created_at: "2026-10-01T00:00:00Z",
      acceptance_effect: "legal_acceptance" as const,
    })),
  };
}

test("draft and unavailable packages never offer legal reacceptance", () => {
  assert.equal(consentReacceptState(pack("draft"), history()).available, false);
  assert.equal(consentReacceptState(null, history()).available, false);
});

test("new published version offers exact required documents even when registration is closed", () => {
  const state = consentReacceptState(pack(), history());
  assert.equal(state.available, true);
  assert.deepEqual(state.accepted_documents, keys.map((key) => ({ key, version: "v2", content_hash: hash })));
});

test("current ledger acceptance suppresses repeat action", () => {
  assert.equal(consentReacceptState(pack(), history("v2")).available, false);
});

test("draft test acknowledgement of matching bytes still requires legal acceptance", () => {
  const old = history("v2");
  old.history = old.history.map((event) => ({ ...event, acceptance_effect: "test_acknowledgement" }));
  assert.equal(consentReacceptState(pack(), old).available, true);
});

test("legacy unknown alone is not treated as current consent", () => {
  const old = history();
  old.history = [];
  assert.equal(consentReacceptState(pack(), old).available, true);
});

test("delayed old-account history cannot apply after token switch, including switch back", async () => {
  let token: string | null = "account-a";
  const guard = createConsentSessionGuard(() => token);
  const oldSession = guard.capture();
  let release!: (value: ConsentHistory) => void;
  const delayed = new Promise<ConsentHistory>((resolve) => { release = resolve; });
  let visible: ConsentHistory | null = null;
  const loading = delayed.then((result) => {
    if (guard.isCurrent(oldSession)) visible = result;
  });
  token = "account-b";
  assert.equal(guard.sync(), true);
  visible = history("account-b");
  release(history("account-a"));
  await loading;
  assert.equal(visible?.history[0].document_version, "account-b");
  token = "account-a";
  guard.sync();
  assert.equal(guard.isCurrent(oldSession), false);
  const returnSession = guard.capture();
  guard.invalidate(); // A queued storage event also invalidates A -> B -> A before a response lands.
  assert.equal(guard.isCurrent(returnSession), false);
});
