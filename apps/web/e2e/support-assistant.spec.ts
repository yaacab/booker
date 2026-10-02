import { expect, test } from "@playwright/test";
import { createHmac } from "node:crypto";
import { API_BASE, DEMO_ACCOUNTS, apiHealth, fetchMe, injectSession, login, seedNegotiation } from "./helpers";

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
  await page.getByLabel("Сообщение помощнику").fill("Мне нужен возврат оплаты, нужен оператор");
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
  const firstExchange = ((await firstSessionResponse.json()) as {
    messages: Array<{ id: string; intent: string; needs_human: boolean }>;
  }).messages[0];
  expect(firstExchange.intent).toBe("money_or_legal");
  expect(firstExchange.needs_human).toBe(true);
  const firstExchangeId = firstExchange.id;
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
  const adminInbox = await request.get(`${API_BASE}/notifications`, {
    headers: { Authorization: `Bearer ${admin.token}` },
  });
  expect(adminInbox.status()).toBe(200);
  expect(((await adminInbox.json()) as { items: Array<{ template?: string; entity_id?: string }> }).items
    .some((item) => item.template === "support.ticket.new" && item.entity_id === createdIds[0]))
    .toBe(true);
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
  const ticketInfo = await ticketDetail.json();
  expect(ticketInfo.id).toBe(createdIds[0]);
  expect(ticketInfo.category).toBe("payment");
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


test("booking help keeps a separate assistant session and sends the linked booking", async ({
  page, request,
}) => {
  expect(await apiHealth(request), `API недоступен (${API_BASE})`).toBe(true);
  const auth = await login(request, DEMO_ACCOUNTS.customer);
  const me = await fetchMe(request, auth.token);
  const org = me.organizations.find((item) => item.kind === "customer");
  expect(org?.id).toBeTruthy();
  await injectSession(page, auth.token, org!.id);

  const bookingId = "11111111-2222-4333-8444-555555555555";
  const linkedSessionId = "66666666-7777-4888-9999-aaaaaaaaaaaa";
  const ordinaryKey = `booker.support.assistantSession.${auth.user_id}.${org!.id}`;
  const linkedKey = `${ordinaryKey}.booking.${bookingId}`;
  await page.evaluate((key) => localStorage.setItem(key, "ordinary-session"), ordinaryKey);
  let createdWith: Record<string, string> | null = null;
  let ordinaryRestored = false;
  await page.route("**/support/assistant/sessions/ordinary-session", async (route) => {
    ordinaryRestored = true;
    await route.fulfill({ status: 500, body: "Unexpected ordinary session restore" });
  });
  await page.route("**/support/assistant/sessions", async (route) => {
    createdWith = route.request().postDataJSON() as Record<string, string>;
    await route.fulfill({ status: 201, contentType: "application/json", body: JSON.stringify({
      id: linkedSessionId, status: "active", related_type: "booking", related_id: bookingId,
      messages: [],
    }) });
  });
  await page.route("**/support/assistant/sessions/*/messages", async (route) => {
    await route.fulfill({ status: 201, contentType: "application/json", body: JSON.stringify({
      id: "bbbbbbbb-cccc-4ddd-8eee-ffffffffffff", user_message: "Какой статус брони?",
      assistant_message: "По связанной брони сервер Букера показывает этап.",
      intent: "booking_flow", outcome: "answered", needs_human: false,
      source_ids: ["support.booking_status"], created_at: new Date().toISOString(),
    }) });
  });

  await page.goto(`/support?booking=${bookingId}`);
  await expect(page.getByRole("link", { name: "Вернуться в Deal Room" })).toBeVisible();
  await page.getByLabel("Сообщение помощнику").fill("Какой статус брони?");
  await page.getByRole("button", { name: "Спросить помощника" }).click();
  await expect(page.getByText(/По связанной брони сервер Букера/)).toBeVisible();
  expect(createdWith).toMatchObject({
    organization_id: org!.id, related_type: "booking", related_id: bookingId,
  });
  expect(ordinaryRestored).toBe(false);
  const stored = await page.evaluate(
    ({ ordinaryKey, linkedKey }) => ({
      ordinary: localStorage.getItem(ordinaryKey), linked: localStorage.getItem(linkedKey),
    }), { ordinaryKey, linkedKey },
  );
  expect(stored).toEqual({ ordinary: "ordinary-session", linked: linkedSessionId });

  await page.route(`**/support/assistant/sessions/${linkedSessionId}`, async (route) => {
    await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({
      id: linkedSessionId, status: "active", related_type: "booking", related_id: bookingId,
      messages: [{ id: "bbbbbbbb-cccc-4ddd-8eee-ffffffffffff", user_message: "Какой статус брони?",
        assistant_message: "По связанной брони сервер Букера показывает этап.",
        intent: "booking_flow", outcome: "answered", needs_human: false,
        source_ids: ["support.booking_status"], created_at: new Date().toISOString() }],
    }) });
  });
  await page.evaluate(() => window.history.pushState(null, "", "/support"));
  await expect(page.getByRole("link", { name: "Вернуться в Deal Room" })).toHaveCount(0);
  await expect(page.getByText(/По связанной брони сервер Букера/)).toHaveCount(0);
  await page.evaluate((id) => window.history.pushState(null, "", `/support?booking=${id}`), bookingId);
  await expect(page.getByRole("link", { name: "Вернуться в Deal Room" })).toBeVisible();
  await expect(page.getByText(/По связанной брони сервер Букера/)).toBeVisible();
});


test("real linked booking reaches support and stays private to its participants", async ({
  page, request,
}) => {
  expect(await apiHealth(request), `API недоступен (${API_BASE})`).toBe(true);
  const deal = await seedNegotiation(request);
  await injectSession(page, deal.customer.token, deal.customer.orgId);
  await page.goto(`/deals/${deal.bookingId}`);
  const help = page.getByRole("link", { name: "Помощь по этой брони" });
  await expect(help).toBeVisible();
  await help.click();
  await expect(page).toHaveURL(new RegExp(`/support\\?booking=${deal.bookingId}$`));
  await page.getByLabel("Сообщение помощнику").fill("Какой статус брони?");
  await page.getByRole("button", { name: "Спросить помощника" }).click();
  await expect(page.getByText(/обсуждение условий/).first()).toBeVisible();

  const key = `booker.support.assistantSession.${deal.customer.user_id}.${deal.customer.orgId}.booking.${deal.bookingId}`;
  const sessionId = await page.evaluate((storageKey) => localStorage.getItem(storageKey), key);
  expect(sessionId).toBeTruthy();
  const own = await request.get(`${API_BASE}/support/assistant/sessions/${sessionId}`, {
    headers: { Authorization: `Bearer ${deal.customer.token}` },
  });
  expect(own.status()).toBe(200);
  const ownSession = await own.json() as {
    related_type: string; related_id: string; messages: Array<{ source_ids: string[] }>;
  };
  expect(ownSession.related_type).toBe("booking");
  expect(ownSession.related_id).toBe(deal.bookingId);
  expect(ownSession.messages[0].source_ids).toContain("support.booking_status");

  const outsider = await login(request, DEMO_ACCOUNTS.customer);
  const denied = await request.get(`${API_BASE}/support/assistant/sessions/${sessionId}`, {
    headers: { Authorization: `Bearer ${outsider.token}` },
  });
  expect(denied.status()).toBe(404);
  const forbiddenLink = await request.post(`${API_BASE}/support/assistant/sessions`, {
    headers: { Authorization: `Bearer ${outsider.token}`, "Idempotency-Key": crypto.randomUUID() },
    data: { related_type: "booking", related_id: deal.bookingId },
  });
  expect(forbiddenLink.status()).toBe(404);
});
