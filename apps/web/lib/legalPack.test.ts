import test from "node:test";
import assert from "node:assert/strict";
import { createHash } from "node:crypto";
import { LEGAL_DOCS, legalDocumentPublicationFromPack, readLegalFile } from "./legal";
import { legalDocumentHref, registrationLegalState, visiblePackDocumentsMatch, type LegalPack } from "./legalPack";

const hash = (value: string) => createHash("sha256").update(value).digest("hex");
const source = "Текст черновика";

function pack(effect: LegalPack["acceptance_effect"] = "test_acknowledgement"): LegalPack {
  const draft = effect === "test_acknowledgement";
  return {
    pack_version: "2026-10-01-draft",
    status: draft ? "draft" : "published",
    registration_available: true,
    acceptance_effect: effect,
    documents: ["offer", "privacy", "consent_texts", "cookies", "disputes", "suppliers", "cancellation"].map((key) => ({
      key: key as LegalPack["documents"][number]["key"], version: "2026-10-01-draft",
      content_hash: hash(source), status: draft ? "draft" : "published",
      required: ["offer", "privacy", "consent_texts"].includes(key),
      href: key === "consent_texts" ? "/legal/consent-texts" : `/legal/${key}`,
    })),
  };
}

test("draft registration uses exact required hashes and explicit test effect", () => {
  const state = registrationLegalState(pack());
  assert.equal(state.available, true);
  assert.equal(state.draftTest, true);
  assert.deepEqual(state.accepted_documents.map((item) => item.key), ["offer", "privacy", "consent_texts"]);
  assert.ok(state.accepted_documents.every((item) => item.content_hash === hash(source)));
  assert.equal(legalDocumentHref("consent_texts"), "/legal/consent-texts");
});

test("production unavailable, missing documents and mismatched states fail closed", () => {
  const unavailable = pack();
  unavailable.registration_available = false;
  assert.equal(registrationLegalState(unavailable).available, false);
  const missing = pack();
  missing.documents.pop();
  assert.equal(registrationLegalState(missing).available, false);
  const invalidHash = pack();
  invalidHash.documents[0].content_hash = "bad";
  assert.equal(registrationLegalState(invalidHash).available, false);
  const mixedVersion = pack();
  mixedVersion.documents[0].version = "older-version";
  assert.equal(registrationLegalState(mixedVersion).available, false);
  const mismatched = pack();
  mismatched.acceptance_effect = "legal_acceptance";
  assert.equal(registrationLegalState(mismatched).available, false);
  const visibleMismatch = pack();
  visibleMismatch.visible_source_match = false;
  assert.equal(registrationLegalState(visibleMismatch).available, false);
});

test("registration blocks when displayed required text differs from API hashes", () => {
  const current = pack();
  const hashes = Object.fromEntries(current.documents.map((document) => [document.key, hash(source)]));
  assert.equal(visiblePackDocumentsMatch(current, hashes), true);
  assert.equal(visiblePackDocumentsMatch(current, { ...hashes, privacy: hash("changed") }), false);
  assert.equal(visiblePackDocumentsMatch(current, { ...hashes, cookies: hash("changed") }), false);
});

test("published pack is accepted only with published required documents", () => {
  const published = pack("legal_acceptance");
  assert.equal(registrationLegalState(published).available, true);
  assert.equal(registrationLegalState(published).draftTest, false);
  published.documents[0].status = "retired";
  assert.equal(registrationLegalState(published).available, false);
});

test("public page never claims publication for unmatched local bytes", () => {
  const published = pack("legal_acceptance");
  assert.equal(legalDocumentPublicationFromPack(published, source, "offer").label, "Опубликован");
  assert.equal(legalDocumentPublicationFromPack(published, "другой текст", "offer").label, "Черновик");
  assert.equal(legalDocumentPublicationFromPack(null, source, "offer").label, "Черновик");
});

test("required local documents match the draft registry bytes and consent text has its own route", async () => {
  const expected: Record<string, string> = {
    OFFER_DRAFT: "17201d86023d35ac9bff4bc5e3e20718ba9fdc36eabf893a88749acdd3179654",
    PRIVACY_DRAFT: "4f9316eabced514702d41bd19c21b0deef6c74833f6f39a7e178045cfc7a6077",
    CONSENT_TEXTS: "015800faa3e0bca87807fd7bd9d7e31702e7cdf08594292a33eeab2f0f4d8c82",
  };
  for (const [stem, digest] of Object.entries(expected)) {
    assert.equal(hash(await readLegalFile(`${stem}.md`)), digest);
  }
  assert.equal(LEGAL_DOCS.find((item) => item.file === "CONSENT_TEXTS.md")?.href, "/legal/consent-texts");
});
