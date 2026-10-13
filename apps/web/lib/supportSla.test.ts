import test from "node:test";
import assert from "node:assert/strict";
import { formatSupportDeadline, supportDeadlineLabel, SUPPORT_HOURS_TEXT, SUPPORT_TARGET_TEXT } from "./supportSla";

test("support window names the owner approved daily Moscow hours without 24/7 promise", () => {
  assert.match(SUPPORT_HOURS_TEXT, /ежедневно 10:00–22:00 МСК/);
  assert.doesNotMatch(SUPPORT_HOURS_TEXT + SUPPORT_TARGET_TEXT, /24\/7|круглосуточ|гарантирован/i);
  assert.match(SUPPORT_TARGET_TEXT, /не гарантия/);
});

test("support deadline is always shown in Moscow time", () => {
  assert.match(formatSupportDeadline("2026-10-03T07:30:00+00:00"), /03\.10\.2026.*10:30 МСК/);
  assert.equal(formatSupportDeadline("invalid"), "");
});

test("answered, closed, or reopened ticket shows the first response target as history", () => {
  const due = "2026-10-03T07:30:00+00:00";
  assert.match(supportDeadlineLabel(due, "open", null, false), /цель первого ответа до 03\.10\.2026.*10:30 МСК/);
  for (const [status, reopenedAt, answered] of [
    ["open", null, true], ["closed", null, false], ["open", "2026-10-04T07:00:00Z", false],
  ] as const) {
    assert.match(supportDeadlineLabel(due, status, reopenedAt, answered),
      /цель первого ответа была до 03\.10\.2026.*новый срок не назначен/);
  }
});
