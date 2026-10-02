import { expect, test } from "@playwright/test";
import { createHmac } from "node:crypto";
import { API_BASE, DEMO_ACCOUNTS, apiHealth, fetchMe, injectSession, login } from "./helpers";

function demoAdminTotp(): string {
  const alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZ234567";
  let bits = "";
  for (const char of "JBSWY3DPEHPK3PXP") {
    bits += alphabet.indexOf(char).toString(2).padStart(5, "0");
  }
  const key = Buffer.from(bits.match(/.{8}/g)!.map((byte) => Number.parseInt(byte, 2)));
  const counter = Buffer.alloc(8);
  counter.writeBigUInt64BE(BigInt(Math.floor(Date.now() / 30_000)));
  const digest = createHmac("sha1", key).update(counter).digest();
  const offset = digest[digest.length - 1] & 0x0f;
  return ((digest.readUInt32BE(offset) & 0x7fffffff) % 1_000_000).toString().padStart(6, "0");
}

test("support assistant answers safely and creates a human ticket on explicit handoff", async ({
  page,
  request,
}) => {
  expect(await apiHealth(request), `API недоступен (${API_BASE})`).toBe(true);

  const session = await login(request, DEMO_ACCOUNTS.customer);
  const me = await fetchMe(request, session.token);
  const org = me.organizations.find((item) => item.kind === "customer");
  expect(org?.id).toBeTruthy();
  await injectSession(page, session.token, org!.id);
  const ticketIds = async () => {
    const response = await request.get(`${API_BASE}/support/tickets`, {
      headers: { Authorization: `Bearer ${session.token}`, "X-Booker-Org": org!.id },
    });
    expect(response.ok()).toBe(true);
    const payload = (await response.json()) as { items: Array<{ id: string }> };
    return new Set(payload.items.map((item) => item.id));
  };
  const before = await ticketIds();

  await page.goto("/support");
  await expect(page.getByRole("heading", { name: "Помощник Букера" })).toBeVisible();
  await page.getByLabel("Сообщение помощнику").fill("Мне нужен возврат оплаты");
  await page.getByRole("button", { name: "Спросить помощника" }).click();

  await expect(page.getByText(/решения по платежам, возвратам/i).first()).toBeVisible();
  await expect(page.getByText("Для продолжения нужен человек.")).toBeVisible();
  expect([...(await ticketIds())].sort()).toEqual([...before].sort());

  const storageKey = `booker.support.assistantSession.${session.user_id}.${org!.id}`;
  const firstSessionId = await page.evaluate((key) => localStorage.getItem(key), storageKey);
  expect(firstSessionId).toBeTruthy();
  const firstSessionResponse = await request.get(
    `${API_BASE}/support/assistant/sessions/${firstSessionId}`,
    { headers: { Authorization: `Bearer ${session.token}` } },
  );
  const firstExchangeId = ((await firstSessionResponse.json()) as {
    messages: Array<{ id: string }>;
  }).messages[0].id;
  const outsider = await login(request, DEMO_ACCOUNTS.artist);
  const outsiderFeedback = await request.post(
    `${API_BASE}/support/assistant/exchanges/${firstExchangeId}/feedback`,
    {
      headers: { Authorization: `Bearer ${outsider.token}` },
      data: { rating: "helpful" },
    },
  );
  expect(outsiderFeedback.status()).toBe(404);
  await page.getByRole("button", { name: "Ответ 1: полезно" }).focus();
  await page.keyboard.press("Enter");
  await expect(page.getByText("Оценка сохранена: полезно.")).toBeVisible();
  const feedbackReplay = await request.post(
    `${API_BASE}/support/assistant/exchanges/${firstExchangeId}/feedback`,
    {
      headers: { Authorization: `Bearer ${session.token}` },
      data: { rating: "helpful", comment: "" },
    },
  );
  expect(feedbackReplay.status()).toBe(200);

  await page.getByRole("button", { name: "Передать человеку" }).click();
  await expect(page.getByRole("status").filter({ hasText: "Передано человеку:" })).toContainText("SUP-");
  await expect(page.getByRole("button", { name: "Передать человеку" })).toBeDisabled();
  await expect(page.getByRole("button", { name: "Спросить помощника" })).toBeDisabled();
  const afterHandoff = await ticketIds();
  const createdIds = [...afterHandoff].filter((id) => !before.has(id));
  expect(createdIds).toHaveLength(1);

  const customerAdminQueue = await request.get(`${API_BASE}/admin/support/tickets`, {
    headers: { Authorization: `Bearer ${session.token}` },
  });
  expect(customerAdminQueue.status()).toBe(403);
  const admin = await login(request, DEMO_ACCOUNTS.admin);
  const adminHeaders = () => ({
    Authorization: `Bearer ${admin.token}`,
    "X-Booker-TOTP": demoAdminTotp(),
  });
  const queue = await request.get(`${API_BASE}/admin/support/tickets`, {
    headers: adminHeaders(),
  });
  expect(queue.status()).toBe(200);
  expect(Array.isArray((await queue.json()).items)).toBe(true);
  const ticketDetail = await request.get(
    `${API_BASE}/admin/support/tickets/${createdIds[0]}`,
    { headers: adminHeaders() },
  );
  expect(ticketDetail.status()).toBe(200);
  expect((await ticketDetail.json()).id).toBe(createdIds[0]);
  const operatorReply = "Ответ оператора по вашему обращению E2E";
  const sent = await request.post(`${API_BASE}/admin/support/tickets/${createdIds[0]}/messages`, {
    headers: { ...adminHeaders(), "Idempotency-Key": `support-e2e-${createdIds[0]}` },
    data: { body: operatorReply },
  });
  expect(sent.status()).toBe(201);

  await page.reload();
  await expect(page.getByText(/решения по платежам, возвратам/i).first()).toBeVisible();
  await expect(page.getByText("Оценка сохранена: полезно.")).toBeVisible();
  await expect(page.getByRole("button", { name: "Передать человеку" })).toBeDisabled();
  await expect(page.getByRole("heading", { name: "Обращение из помощника Букера" })).toBeVisible();
  await expect(page.getByText(operatorReply)).toBeVisible();
  await page.getByLabel("Ответ в поддержку").fill("Дополнительные сведения для оператора");
  await page.getByRole("button", { name: "Отправить сообщение" }).click();
  await expect(page.getByText("Дополнительные сведения для оператора")).toBeVisible();

  await page.getByRole("button", { name: "Закрыть обращение" }).click();
  await expect(page.getByRole("button", { name: "Открыть повторно" })).toBeVisible();
  await page.getByRole("button", { name: "Открыть повторно" }).click();
  await expect(page.getByLabel("Ответ в поддержку")).toBeVisible();

  await page.setViewportSize({ width: 390, height: 844 });
  await page.getByRole("button", { name: "Новый вопрос помощнику" }).click();
  await expect(page.getByLabel("Сообщение помощнику")).toBeFocused();
  await expect(page.getByRole("heading", { name: "Обращение из помощника Букера" })).toBeVisible();
  await page.getByLabel("Сообщение помощнику").fill("Не могу войти в кабинет");
  await page.getByRole("button", { name: "Спросить помощника" }).click();
  await expect(page.getByText(/Проверьте адрес почты/)).toBeVisible();
  const secondSessionId = await page.evaluate((key) => localStorage.getItem(key), storageKey);
  expect(secondSessionId).toBeTruthy();
  expect(secondSessionId).not.toBe(firstSessionId);
  expect([...(await ticketIds())].sort()).toEqual([...afterHandoff].sort());
});
