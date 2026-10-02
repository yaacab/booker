import test from "node:test";
import assert from "node:assert/strict";
import {
  DATA_SUBJECT_TYPES, availableDataSubjectTransitions, dataSubjectError, dataSubjectHeaders, dataSubjectPath,
  dataSubjectListPath, dataSubjectReasonForStatus,
  dataSubjectStatusLabel, dataSubjectTypeLabel,
} from "./dataSubject";

test("user and admin request paths encode untrusted IDs", () => {
  assert.equal(dataSubjectPath("a/b"), "/data-subject/requests/a%2Fb");
  assert.equal(dataSubjectPath("a/b", true, "/deletion-plan"), "/admin/data-subject/requests/a%2Fb/deletion-plan");
  assert.equal(dataSubjectListPath(40), "/data-subject/requests?limit=20&offset=40");
  assert.equal(dataSubjectListPath(20, true, "needs_info"),
    "/admin/data-subject/requests?limit=20&offset=20&request_status=needs_info");
});

test("TOTP, CAS version and idempotency key are headers", () => {
  const headers = dataSubjectHeaders(" 123456 ", 3, "create-key-123");
  assert.equal(headers.get("X-Booker-TOTP"), "123456");
  assert.equal(headers.get("If-Match"), "3");
  assert.equal(headers.get("Idempotency-Key"), "create-key-123");
  assert.equal(dataSubjectHeaders("", 0).has("X-Booker-TOTP"), false);
});

test("public labels cover supported requests without deadline promises", () => {
  assert.deepEqual(DATA_SUBJECT_TYPES, ["access", "export", "restrict", "delete", "correct"]);
  assert.equal(dataSubjectTypeLabel("delete"), "Удаление данных");
  assert.equal(dataSubjectStatusLabel("in_review"), "На рассмотрении");
  assert.equal(dataSubjectStatusLabel("unknown"), "Статус уточняется");
  assert.doesNotMatch(dataSubjectError(409), /дней|часов|гарант/i);
  assert.match(dataSubjectError(409), /обновлены/);
});

test("admin offers only transitions the bounded backend can execute", () => {
  const base = { id: "request", request_type: "delete", status: "approved", state_version: 2 };
  assert.deepEqual(availableDataSubjectTransitions(base), []);
  assert.deepEqual(availableDataSubjectTransitions({ ...base, request_type: "restrict" }), ["completed"]);
  assert.deepEqual(availableDataSubjectTransitions({ ...base, status: "in_review", active_hold: true }), ["needs_info", "rejected"]);
  assert.equal(dataSubjectReasonForStatus("rejected"), "scope_rejected");
});
