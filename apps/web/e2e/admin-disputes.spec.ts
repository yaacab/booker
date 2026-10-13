import { expect, test } from "@playwright/test";

test("оператор назначает и завершает спор через защищённую очередь", async ({ page }) => {
  let status: "open" | "in_review" | "resolved" = "open";
  let assignedTo: string | null = null;
  let stateVersion = 0;
  let decisionKind: string | null = null;
  let decisionNote = "";
  const mutationBodies: Record<string, unknown>[] = [];

  const dispute = () => ({
    id: "dispute-e2e",
    booking_id: "booking-e2e",
    assigned_to_user_id: assignedTo,
    category: "payment",
    notes: "Оплата требует проверки",
    status,
    priority: "urgent",
    response_due_at: "2026-10-01T15:00:00+03:00",
    state_version: stateVersion,
    decision_kind: decisionKind,
    decision_note: decisionNote,
    created_at: "2026-10-01T13:00:00+03:00",
    evidence: [
      {
        id: "evidence-e2e",
        attachment_id: "attachment-e2e",
        note: "Чек",
        created_at: "2026-10-01T13:05:00+03:00",
      },
    ],
  });

  await page.addInitScript(() => localStorage.setItem("booker.token", "operator-token"));
  await page.route("**/me", (route) =>
    route.fulfill({ json: { id: "operator-e2e", totp_enabled: true } }),
  );
  await page.route("**/admin/verifications", (route) =>
    route.fulfill({ json: { queue: [], artists: [], venues: [] } }),
  );
  await page.route("**/admin/audit", (route) => route.fulfill({ json: { items: [] } }));
  await page.route("**/admin/metrics", (route) =>
    route.fulfill({ json: { periods: { "7": {}, "30": {} } } }),
  );
  await page.route("**/admin/venue-catalog/venues?limit=50", (route) =>
    route.fulfill({ json: { items: [] } }),
  );
  await page.route("**/admin/venue-catalog/report", (route) =>
    route.fulfill({
      json: {
        total: 0,
        automated: 0,
        unverified: 0,
        verified: 0,
        partners: 0,
        published: 0,
        needs_review: 0,
      },
    }),
  );
  await page.route("**/admin/disputes", (route) =>
    route.fulfill({ json: { items: [dispute()] } }),
  );
  await page.route("**/admin/disputes/dispute-e2e/assignment", async (route) => {
    const body = route.request().postDataJSON() as Record<string, unknown>;
    mutationBodies.push(body);
    assignedTo = String(body.assignee_user_id);
    status = "in_review";
    stateVersion += 1;
    await route.fulfill({ json: dispute() });
  });
  await page.route("**/admin/disputes/dispute-e2e/resolve", async (route) => {
    const body = route.request().postDataJSON() as Record<string, unknown>;
    mutationBodies.push(body);
    decisionKind = String(body.decision_kind);
    decisionNote = String(body.decision_note);
    status = "resolved";
    stateVersion += 1;
    await route.fulfill({ json: { ...dispute(), automatic_money_movement: false } });
  });

  await page.goto("/admin");
  const caseCard = page.getByRole("region", { name: "Спор dispute-e2e" });
  await expect(caseCard.getByText("Оплата требует проверки")).toBeVisible();
  await expect(caseCard.getByText("доказательств: 1", { exact: false })).toBeVisible();

  await page.getByLabel("Код TOTP для назначения и решения").fill("123456");
  await caseCard.getByRole("button", { name: "Взять в работу" }).click();
  await expect(caseCard.getByLabel("Решение")).toBeVisible();
  expect(mutationBodies[0]).toMatchObject({
    assignee_user_id: "operator-e2e",
    state_version: 0,
    totp: "123456",
  });

  await page.getByLabel("Код TOTP для назначения и решения").fill("654321");
  await caseCard.getByLabel("Решение").selectOption("refund_review_required");
  await caseCard.getByLabel("Основание решения").fill("Передать на отдельную проверку возврата");
  await caseCard.getByRole("button", { name: "Завершить рассмотрение" }).click();

  await expect(caseCard.getByText("Статус: решён", { exact: false })).toBeVisible();
  await expect(
    caseCard.locator("strong").filter({ hasText: "Передать на отдельную проверку возврата" }),
  ).toBeVisible();
  expect(mutationBodies[1]).toMatchObject({
    decision_kind: "refund_review_required",
    state_version: 1,
    totp: "654321",
  });
});
