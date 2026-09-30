import { expect, test } from "@playwright/test";
import {
  BLOCKER_LABEL,
  buildNextSteps,
  dayOpsVisible,
  isClosedRequest,
  needsReplacement,
  openLooseRequests,
  roleBlocker,
} from "../lib/eventDayOps";

const reqDj = { id: "req-dj", category_code: "dj", qty: 2 };
const reqHost = { id: "req-host", category_code: "host", qty: 1 };

test.describe("eventDayOps", () => {
  test("isClosedRequest: only actual confirmed booking states", () => {
    expect(isClosedRequest({ id: "1", status: "Negotiation", booking_id: "b1" })).toBe(false);
    expect(isClosedRequest({ id: "held", status: "Negotiation", booking_id: "b1", booking_status: "DateHeld" })).toBe(false);
    expect(isClosedRequest({ id: "cancelled", status: "Confirmed", booking_id: "b1", booking_status: "Cancelled" })).toBe(false);
    expect(isClosedRequest({ id: "live", status: "Negotiation", booking_id: "b1", booking_status: "InProgress" })).toBe(true);
    expect(isClosedRequest({ id: "2", status: "Confirmed" })).toBe(true);
    expect(isClosedRequest({ id: "3", status: "Negotiation" })).toBe(false);
  });

  test("roleBlocker: pipeline stages", () => {
    expect(roleBlocker([], 1)).toBe("no_request");
    expect(roleBlocker([{ id: "1", status: "RequestSent" }], 1)).toBe("no_offer");
    expect(
      roleBlocker([{ id: "1", status: "Negotiation", quote_id: "q1" }], 1),
    ).toBe("no_booking");
    expect(
      roleBlocker(
        [
          { id: "1", status: "Confirmed", booking_id: "b1" },
          { id: "2", status: "RequestSent" },
        ],
        2,
      ),
    ).toBe("no_offer");
  });

  test("buildNextSteps: only open roles with blocker text", () => {
    const steps = buildNextSteps(
      [reqDj, reqHost],
      [
        { id: "r1", status: "Confirmed", booking_id: "b1", requirement_id: "req-dj" },
        { id: "r2", status: "RequestSent", requirement_id: "req-dj" },
        { id: "r3", status: "Negotiation", quote_id: "q1", requirement_id: "req-host" },
      ],
      (req) => req.category_code,
    );
    expect(steps).toHaveLength(2);
    expect(steps[0].blocker).toBe("no_offer");
    expect(BLOCKER_LABEL[steps[0].blocker]).toBe("дождитесь предложения артиста");
    expect(steps[1].openRequests).toHaveLength(1);
    expect(steps[1].blocker).toBe("no_booking");
  });

  test("needsReplacement: cancelled open request", () => {
    const steps = buildNextSteps(
      [reqDj],
      [{ id: "r1", status: "Cancelled", requirement_id: "req-dj" }],
      (req) => req.category_code,
    );
    expect(steps).toHaveLength(1);
    expect(needsReplacement(steps[0])).toBe(true);
  });

  test("cancelled booking overrides old request status for replacement", () => {
    const steps = buildNextSteps([reqDj], [{ id: "old", status: "Confirmed", booking_status: "Cancelled", requirement_id: reqDj.id }], req => req.category_code);
    expect(needsReplacement(steps[0])).toBe(true);
    expect(steps[0].blocker).toBe("no_request");
  });

  test("openLooseRequests: unmatched without booking", () => {
    const loose = openLooseRequests(
      [
        { id: "x", status: "Negotiation", requirement_id: null },
        { id: "y", status: "Confirmed", booking_id: "b", requirement_id: null },
      ],
      [reqDj],
    );
    expect(loose.map((item) => item.id)).toEqual(["x"]);
  });

  test("dayOpsVisible: only when bookings exist", () => {
    expect(dayOpsVisible(null)).toBe(false);
    expect(
      dayOpsVisible({
        event_status: "Confirmed",
        can_event_check_in: true,
        can_event_check_out: false,
        bookings: [],
        summary: { confirmed: 0, in_progress: 0, completed: 0, total: 0 },
      }),
    ).toBe(false);
    expect(
      dayOpsVisible({
        event_status: "InProgress",
        can_event_check_in: false,
        can_event_check_out: true,
        bookings: [
          {
            booking_id: "b1",
            booking_status: "InProgress",
            can_check_in: false,
            can_check_out: true,
          },
        ],
        summary: { confirmed: 0, in_progress: 1, completed: 0, total: 1 },
      }),
    ).toBe(true);
  });
});
