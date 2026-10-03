import test from "node:test";
import assert from "node:assert/strict";
import {
  safeSupportSubject,
  supportQueueAge,
  stableSupportKey,
  supportQueueHeaders,
  supportQueuePath,
  supportTicketPath,
} from "./supportQueue";

test("queue filters are encoded and do not put TOTP in the URL", () => {
  const path = supportQueuePath({
    state: "waiting_for_support", overdue: true, priority: "urgent", category: "payment",
    assignedToMe: true, limit: 20, offset: 40,
  });
  const query = new URLSearchParams(path.split("?")[1]);
  assert.equal(query.get("state"), "waiting_for_support");
  assert.equal(query.get("overdue_only"), "true");
  assert.equal(query.get("priority"), "urgent");
  assert.equal(query.get("category"), "payment");
  assert.equal(query.get("assigned_to_me"), "true");
  assert.equal(query.get("limit"), "20");
  assert.equal(query.get("offset"), "40");
  const unfiltered = supportQueuePath({
    state: "all", overdue: false, priority: "all", category: "all",
    assignedToMe: false, limit: 20, offset: 0,
  });
  assert.equal(new URLSearchParams(unfiltered.split("?")[1]).has("priority"), false);
  assert.equal(new URLSearchParams(unfiltered.split("?")[1]).has("category"), false);
  assert.doesNotMatch(path, /123456/);
  assert.equal(supportTicketPath("a/b", "/notes"), "/admin/support/tickets/a%2Fb/notes");
});

test("queue age uses the creation instant and stays bounded for malformed input", () => {
  const now = Date.parse("2026-10-03T11:30:00Z");
  assert.equal(supportQueueAge("2026-10-03T10:00:00Z", now), "1 ч 30 мин");
  assert.equal(supportQueueAge("2026-10-01T09:00:00Z", now), "2 д 2 ч");
  assert.equal(supportQueueAge("invalid", now), "Возраст неизвестен");
});

test("TOTP, version and idempotency key use separate headers", () => {
  const headers = supportQueueHeaders(" 123456 ", 7, "retry-key-123");
  assert.equal(headers.get("X-Booker-TOTP"), "123456");
  assert.equal(headers.get("If-Match"), "7");
  assert.equal(headers.get("Idempotency-Key"), "retry-key-123");
});

test("reply key stays stable for retry and rotates when payload changes", () => {
  let count = 0;
  const makeKey = () => `request-${++count}`;
  const first = stableSupportKey(null, "reply:ticket-1:hello", makeKey);
  const replay = stableSupportKey(first, "reply:ticket-1:hello", makeKey);
  const changed = stableSupportKey(replay, "reply:ticket-1:hello again", makeKey);
  assert.equal(first.key, replay.key);
  assert.notEqual(first.key, changed.key);
  assert.equal(count, 2);
});

test("subject is plain bounded text even when stored value contains controls", () => {
  assert.equal(safeSupportSubject("  Срочно\n\t<script>alert(1)</script>  "), "Срочно <script>alert(1)</script>");
  assert.equal(safeSupportSubject("\u0000"), "Без темы");
  assert.equal(safeSupportSubject("x".repeat(150)).length, 120);
});
