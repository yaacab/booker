import { expect, test } from "@playwright/test";
import {
  API_BASE,
  apiHealth,
  getJson,
  injectSession,
  seedRequestAwaitingOffer,
} from "./helpers";

type InboxResponse = {
  items: Array<{
    request_id: string;
    booking_id: string | null;
    deal_path: string | null;
    can_write: boolean;
  }>;
};

test("request conversation works before an offer and remains separate from support", async ({
  page,
  request,
}) => {
  expect(await apiHealth(request), `API недоступен (${API_BASE})`).toBe(true);
  const seed = await seedRequestAwaitingOffer(request);

  await test.step("supplier opens the request-only conversation and replies", async () => {
    await injectSession(page, seed.ownerToken, seed.artistOrgId);
    await page.goto("/cabinet/performer/messages");
    const thread = page.getByRole("article").filter({ hasText: seed.eventTitle }).first();
    await expect(thread).toBeVisible({ timeout: 15_000 });
    await expect(thread.getByRole("link", { name: "Открыть Deal Room" })).toHaveCount(0);
    await thread.getByRole("button", { name: "Открыть переписку" }).click();
    const conversation = thread.getByRole("region", { name: `Переписка: ${seed.eventTitle}` });
    await expect(conversation.getByText("Заявка отправлена", { exact: false })).toBeVisible();
    await conversation
      .getByRole("textbox", { name: "Сообщение по заявке" })
      .fill("Уточните время монтажа");
    await conversation.getByRole("button", { name: "Отправить" }).click();
    await expect(conversation.getByText("Уточните время монтажа", { exact: false })).toBeVisible();
    await expect(conversation.getByText(/^Исполнитель · /)).toBeVisible();
  });

  await test.step("customer reads the same conversation without creating a booking", async () => {
    const inbox = await getJson<InboxResponse>(
      request,
      "/messages/inbox",
      seed.customerToken,
      seed.customerOrgId,
    );
    const item = inbox.items.find((candidate) => candidate.request_id === seed.requestId);
    expect(item).toMatchObject({ booking_id: null, deal_path: null, can_write: true });

    await injectSession(page, seed.customerToken, seed.customerOrgId);
    await page.goto("/cabinet/customer/messages");
    const thread = page.getByRole("article").filter({ hasText: seed.eventTitle });
    await thread.getByRole("button", { name: "Открыть переписку" }).click();
    const conversation = thread.getByRole("region", { name: `Переписка: ${seed.eventTitle}` });
    await expect(conversation.getByText("Уточните время монтажа", { exact: false })).toBeVisible();
    await expect(conversation.getByText(/^Исполнитель · /)).toBeVisible();
  });
});
