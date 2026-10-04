import { expect, test, type APIRequestContext } from "@playwright/test";
import {
  API_BASE,
  apiHealth,
  getJson,
  postJson,
  seedNegotiation,
} from "./helpers";

type DraftContract = {
  id: string;
  body: string;
  body_sha256: string;
  offer_version_id: string;
  effect: string;
};

async function latestContractCode(
  request: APIRequestContext,
  token: string,
  contractId: string,
): Promise<string> {
  const inbox = await getJson<{
    items: Array<{ channel: string; entity_id: string; body?: string }>;
  }>(request, "/notifications?limit=100", token);
  const body = inbox.items.find(
    (item) => item.channel === "in_app" && item.entity_id === contractId,
  )?.body ?? "";
  const code = body.match(/\b(\d{6})\b/)?.[1];
  if (!code) {
    throw new Error(`Contract acknowledgement code is missing from the private inbox: ${JSON.stringify(inbox)}`);
  }
  return code;
}

test("immutable draft is acknowledged by both actors with the displayed hash", async ({ page, request }) => {
  test.setTimeout(120_000);
  test.skip(!(await apiHealth(request)), `API недоступен (${API_BASE})`);

  const ctx = await seedNegotiation(request, {
    honorariumRub: 107_000,
    terms: "E2E: точный технический черновик",
  });
  await postJson(
    request,
    `/offers/${ctx.offerId}/ack`,
    ctx.owner.token,
    { side: "supplier", quote_id: ctx.quoteId },
    ctx.owner.orgId,
  );
  await postJson(
    request,
    `/offers/${ctx.offerId}/ack`,
    ctx.customer.token,
    { side: "customer", quote_id: ctx.quoteId },
    ctx.customer.orgId,
  );
  await postJson(request, `/bookings/${ctx.bookingId}/hold`, ctx.customer.token, {}, ctx.customer.orgId);
  const contract = await postJson<DraftContract>(
    request,
    `/bookings/${ctx.bookingId}/contract`,
    ctx.customer.token,
    {},
    ctx.customer.orgId,
  );
  expect(contract.effect).toBe("technical_draft_acknowledgement");
  expect(contract.offer_version_id).toBe(ctx.quoteId);
  expect(contract.body).toContain(ctx.eventTitle);
  expect(contract.body).toContain(ctx.terms);
  const customerCode = await latestContractCode(request, ctx.customer.token, contract.id);
  const supplierCode = await latestContractCode(request, ctx.owner.token, contract.id);

  await page.goto("/");
  await page.evaluate(
    ({ token, orgId }) => {
      localStorage.setItem("booker.token", token);
      localStorage.setItem("booker.org", orgId);
    },
    { token: ctx.customer.token, orgId: ctx.customer.orgId },
  );
  await page.goto(`/deals/${ctx.bookingId}`);
  await page.getByRole("tab", { name: "Документы" }).click();
  await expect(page.getByText(`SHA-256: ${contract.body_sha256}`)).toBeVisible({ timeout: 15_000 });
  await expect(page.getByText(/Юридическая сила простой электронной подписи не утверждена/)).toBeVisible();
  await expect(page.getByText(/договор подписан/i)).toHaveCount(0);
  await page.getByRole("button", { name: "Запросить новый код" }).first().click();
  await expect(page.getByText("Текущий код ещё действует")).toBeVisible();
  await page.getByLabel("Код технического подтверждения черновика").fill(customerCode);
  await page.getByRole("button", { name: "Подтвердить черновик по коду" }).click();
  await page.getByRole("tab", { name: "Документы" }).click();
  await expect(page.getByText(/Заказчик: техническое подтверждение/)).toBeVisible({ timeout: 15_000 });

  await page.evaluate(
    ({ token, orgId }) => {
      localStorage.setItem("booker.token", token);
      localStorage.setItem("booker.org", orgId);
    },
    { token: ctx.owner.token, orgId: ctx.owner.orgId },
  );
  await page.reload();
  await page.getByRole("tab", { name: "Документы" }).click();
  await page.getByLabel("Код технического подтверждения черновика").fill(supplierCode);
  await page.getByRole("button", { name: "Подтвердить черновик по коду" }).click();
  await page.getByRole("tab", { name: "Сводка" }).click();
  await expect(page.getByText(/черновик технически подтверждён обеими сторонами/)).toBeVisible({ timeout: 15_000 });

  const room = await getJson<{
    status: string;
    contract: {
      body_sha256: string;
      acknowledgements: Array<{ side: string; body_sha256: string; effect: string }>;
    };
  }>(request, `/deal-room/${ctx.bookingId}`, ctx.customer.token, ctx.customer.orgId);
  expect(room.status).toBe("AwaitingPayment");
  expect(room.contract.acknowledgements.map((item) => item.side).sort()).toEqual(["customer", "supplier"]);
  expect(room.contract.acknowledgements.every(
    (item) => item.body_sha256 === contract.body_sha256
      && item.effect === "technical_draft_acknowledgement",
  )).toBe(true);

  await page.setViewportSize({ width: 390, height: 844 });
  await page.getByRole("tab", { name: "Документы" }).click();
  await expect(page.getByText(`SHA-256: ${contract.body_sha256}`)).toBeVisible();
});
