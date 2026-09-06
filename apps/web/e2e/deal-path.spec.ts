import { expect, test } from "@playwright/test";
import {
  API_BASE,
  apiHealth,
  getJson,
  injectSession,
  postJson,
  seedNegotiation,
  seedRequestAwaitingOffer,
  seedSameSlotHoldRace,
} from "./helpers";

type DealRoomQuote = {
  quote_id: string;
  honorarium_rub: number;
  total_rub: number;
  customer_ack?: boolean;
  supplier_ack?: boolean;
  terms?: string;
  active?: boolean;
};

test.describe("Deal path E07–E09", () => {
  test.setTimeout(120_000);

  test("E07: заявка → оффер — одна сущность, одинаковые условия с обеих сторон", async ({
    page,
    request,
  }) => {
    test.skip(!(await apiHealth(request)), `API недоступен (${API_BASE})`);

    const seed = await seedRequestAwaitingOffer(request);
    // seedRequestAwaitingOffer не отдаёт customer — добираем через negotiation seed pattern
    // Здесь UI-path: артист шлёт оффер, затем обе стороны видят один quote_id.
    const negotiation = await seedNegotiation(request, {
      honorariumRub: 88_000,
      terms: "E07: общий quote",
      slotStartsAt: "2026-12-01T18:00:00+00:00",
      slotEndsAt: "2026-12-01T22:00:00+00:00",
    });

    await test.step("supplier: Deal Room показывает quote_id и гонорар", async () => {
      await injectSession(page, negotiation.owner.token, negotiation.owner.orgId);
      await page.goto(`/deals/${negotiation.bookingId}`);
      await expect(page.getByTestId("deal-room-accents")).toBeVisible({ timeout: 15_000 });
      await expect(page.getByText(`quote_id: ${negotiation.quoteId}`).first()).toBeVisible();
      await expect(
        page.getByText(negotiation.honorariumRub.toLocaleString("ru-RU"), { exact: false }).first(),
      ).toBeVisible();
    });

    await test.step("API: customer и supplier видят один и тот же quote", async () => {
      const supplierRoom = await getJson<{ offer_id: string; quote: DealRoomQuote }>(
        request,
        `/deal-room/${negotiation.bookingId}`,
        negotiation.owner.token,
        negotiation.owner.orgId,
      );
      const customerRoom = await getJson<{ offer_id: string; quote: DealRoomQuote }>(
        request,
        `/deal-room/${negotiation.bookingId}`,
        negotiation.customer.token,
        negotiation.customer.orgId,
      );

      expect(supplierRoom.offer_id).toBe(negotiation.offerId);
      expect(customerRoom.offer_id).toBe(negotiation.offerId);
      expect(supplierRoom.quote.quote_id).toBe(negotiation.quoteId);
      expect(customerRoom.quote.quote_id).toBe(negotiation.quoteId);
      expect(supplierRoom.quote.honorarium_rub).toBe(negotiation.honorariumRub);
      expect(customerRoom.quote.honorarium_rub).toBe(negotiation.honorariumRub);
      expect(customerRoom.quote.total_rub).toBe(supplierRoom.quote.total_rub);
    });

    await test.step("customer UI: те же условия в Deal Room", async () => {
      await injectSession(page, negotiation.customer.token, negotiation.customer.orgId);
      await page.goto(`/deals/${negotiation.bookingId}`);
      await expect(page.getByTestId("deal-room-accents")).toBeVisible({ timeout: 15_000 });
      await expect(page.getByText(`quote_id: ${negotiation.quoteId}`).first()).toBeVisible();
      await expect(page.getByRole("heading", { name: "Итог" })).toBeVisible();
    });

    // UI-path из awaiting-offer (как flow.spec) — общий booking после кнопки
    await test.step("UI path: артист отправляет предложение из кабинета", async () => {
      await injectSession(page, seed.ownerToken, seed.artistOrgId);
      await page.goto("/cabinet");
      await expect(page.getByRole("heading", { name: "Новые заявки" })).toBeVisible({ timeout: 15_000 });
      await expect(page.getByText(seed.eventTitle)).toBeVisible();
      await page.getByRole("button", { name: "Отправить предложение" }).click();
      await expect(page).toHaveURL(/\/deals\//, { timeout: 15_000 });
      const bookingId = page.url().split("/deals/")[1]?.split(/[?#]/)[0] ?? "";
      expect(bookingId).toBeTruthy();
      await expect(page.getByTestId("deal-room-accents")).toBeVisible();
      await expect(page.getByText("quote_id:").first()).toBeVisible();
    });
  });

  test("E08: новая версия сбрасывает ack — hold 409 до re-ack обеих сторон", async ({
    page,
    request,
  }) => {
    test.skip(!(await apiHealth(request)), `API недоступен (${API_BASE})`);

    const ctx = await seedNegotiation(request, {
      honorariumRub: 100_000,
      terms: "E08 v1",
      slotStartsAt: "2026-12-08T18:00:00+00:00",
      slotEndsAt: "2026-12-08T22:00:00+00:00",
    });

    await test.step("v1: двусторонний ack", async () => {
      await postJson(request, `/offers/${ctx.offerId}/ack`, ctx.owner.token, { side: "supplier" }, ctx.owner.orgId);
      await postJson(
        request,
        `/offers/${ctx.offerId}/ack`,
        ctx.customer.token,
        { side: "customer" },
        ctx.customer.orgId,
      );
      const room = await getJson<{ quote: DealRoomQuote }>(
        request,
        `/deal-room/${ctx.bookingId}`,
        ctx.customer.token,
        ctx.customer.orgId,
      );
      expect(room.quote.supplier_ack).toBe(true);
      expect(room.quote.customer_ack).toBe(true);
      expect(room.quote.quote_id).toBe(ctx.quoteId);
    });

    const v2 = await test.step("v2: новая смета, старые ack не действуют", async () => {
      const bumped = await postJson<{
        id: string;
        quote_id: string;
        honorarium_rub: number;
        active: boolean;
      }>(
        request,
        `/offers/${ctx.offerId}/versions`,
        ctx.owner.token,
        { honorarium_rub: 120_000, terms: "E08 v2: новая смета" },
        ctx.owner.orgId,
      );
      expect(bumped.active).toBe(false);
      expect(bumped.quote_id).toBe(bumped.id);
      expect(bumped.quote_id).not.toBe(ctx.quoteId);
      expect(bumped.honorarium_rub).toBe(120_000);

      const room = await getJson<{ quote: DealRoomQuote }>(
        request,
        `/deal-room/${ctx.bookingId}`,
        ctx.customer.token,
        ctx.customer.orgId,
      );
      expect(room.quote.quote_id).toBe(bumped.quote_id);
      expect(room.quote.customer_ack).toBe(false);
      expect(room.quote.supplier_ack).toBe(false);
      return bumped;
    });

    await test.step("hold 409 без re-ack", async () => {
      const hold = await request.post(`${API_BASE}/bookings/${ctx.bookingId}/hold`, {
        headers: {
          Authorization: `Bearer ${ctx.customer.token}`,
          "Content-Type": "application/json",
          "X-Booker-Org": ctx.customer.orgId,
        },
      });
      expect(hold.status()).toBe(409);
    });

    await test.step("только supplier re-ack — hold всё ещё 409", async () => {
      await injectSession(page, ctx.owner.token, ctx.owner.orgId);
      await page.goto(`/deals/${ctx.bookingId}`);
      await expect(page.getByTestId("deal-room-accents")).toBeVisible({ timeout: 15_000 });
      await page.getByRole("button", { name: "Подтвердить условия" }).click();
      await expect(page.getByText("подтвердил только исполнитель").first()).toBeVisible({ timeout: 10_000 });

      const hold = await request.post(`${API_BASE}/bookings/${ctx.bookingId}/hold`, {
        headers: {
          Authorization: `Bearer ${ctx.customer.token}`,
          "Content-Type": "application/json",
          "X-Booker-Org": ctx.customer.orgId,
        },
      });
      expect(hold.status()).toBe(409);
    });

    await test.step("customer re-ack → hold 200; UI показывает удержание", async () => {
      await injectSession(page, ctx.customer.token, ctx.customer.orgId);
      await page.goto(`/deals/${ctx.bookingId}`);
      await expect(page.getByText(`quote_id: ${v2.quote_id}`).first()).toBeVisible({ timeout: 15_000 });
      await page.getByRole("button", { name: "Подтвердить условия" }).click();
      await expect(page.getByText("подтверждено обеими сторонами").first()).toBeVisible({ timeout: 10_000 });

      await page.getByRole("button", { name: "Удержать дату" }).click();
      await expect(page.getByText("Дата удерживается").first()).toBeVisible({ timeout: 10_000 });

      const room = await getJson<{ hold?: { status: string }; quote: DealRoomQuote }>(
        request,
        `/deal-room/${ctx.bookingId}`,
        ctx.customer.token,
        ctx.customer.orgId,
      );
      expect(room.hold?.status).toBe("active");
      expect(room.quote.quote_id).toBe(v2.quote_id);
      expect(room.quote.honorarium_rub).toBe(120_000);
    });
  });

  test("E09: два hold на один слот — ровно один 200 и один 409", async ({ request }) => {
    test.skip(!(await apiHealth(request)), `API недоступен (${API_BASE})`);

    const race = await seedSameSlotHoldRace(request);

    const first = await request.post(`${API_BASE}/bookings/${race.bookingId}/hold`, {
      headers: {
        Authorization: `Bearer ${race.customer.token}`,
        "Content-Type": "application/json",
        "X-Booker-Org": race.customer.orgId,
      },
    });
    const second = await request.post(`${API_BASE}/bookings/${race.bookingId2}/hold`, {
      headers: {
        Authorization: `Bearer ${race.customer2.token}`,
        "Content-Type": "application/json",
        "X-Booker-Org": race.customer.orgId,
      },
    });

    expect(sortedStatuses([first.status(), second.status()])).toEqual([200, 409]);

    // stub payments only — не проверяем PSP; exclusivity слота достаточна
    const winnerId = first.status() === 200 ? race.bookingId : race.bookingId2;
    const winnerToken = first.status() === 200 ? race.customer.token : race.customer2.token;
    const room = await getJson<{ status: string; hold?: { status: string } }>(
      request,
      `/deal-room/${winnerId}`,
      winnerToken,
      race.customer.orgId,
    );
    expect(room.hold?.status).toBe("active");
  });
});

function sortedStatuses(codes: number[]): number[] {
  return [...codes].sort((a, b) => a - b);
}
