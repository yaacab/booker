import test from "node:test";
import assert from "node:assert/strict";
import { contractDraftAckBody, contractDraftStatus, type ContractDraftEvidence } from "./contractDraft";

const draft: ContractDraftEvidence = {
  id: "contract-1",
  body: "exact displayed text",
  body_sha256: "a".repeat(64),
  offer_version_id: "quote-1",
  template_version: "direct_draft_v2",
  legal_pack_version: "2026-10-01-draft",
  effect: "technical_draft_acknowledgement",
};

test("technical draft acknowledgement sends the exact displayed snapshot hash", () => {
  assert.deepEqual(contractDraftAckBody(draft, " 123456 "), {
    otp: "123456",
    body_hash: "a".repeat(64),
  });
});

test("legacy or unbound contract cannot be acknowledged from the UI", () => {
  assert.throws(() => contractDraftAckBody({ ...draft, body_sha256: null }, "123456"), /снимку/);
  assert.throws(() => contractDraftAckBody({ ...draft, effect: "legacy_unbound" }, "123456"), /не допускает/);
});

test("status copy never calls a technical acknowledgement a legal signature", () => {
  assert.equal(contractDraftStatus(true), "технически подтверждено");
  assert.equal(contractDraftStatus(false), "черновик ожидает подтверждения");
});
