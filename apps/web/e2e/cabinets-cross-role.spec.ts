import { expect, test } from "@playwright/test";
import {
  API_BASE,
  apiHealth,
  DEMO_ACCOUNTS,
  getJson,
  injectSession,
  login,
  postJson,
  seedCrossRoleEvent,
} from "./helpers";

test.describe("Cross-role E2E §7.5.11", () => {
  test.setTimeout(120_000);

  test("полный цикл: customer → performer + venue → offers → ack → hold → cancel одной позиции", async ({
    page,
    request,
  }) => {
    test.skip(!(await apiHealth(request)), `API недоступен (${API_BASE})`);

    const ctx = await seedCrossRoleEvent(request);
    let artistBookingId = "";
    let venueBookingId = "";
    let artistOfferId = "";

    await test.step("performer: заявка и OfferVersion через UI", async () => {
      await injectSession(page, ctx.artist.token, ctx.artist.orgId);
      await page.goto("/cabinet/performer");
      await expect(page.getByRole("heading", { name: "Новые заявки" })).toBeVisible({ timeout: 15_000 });
      await expect(page.getByText(ctx.eventTitle)).toBeVisible();
      await page
        .getByRole("article")
        .filter({ hasText: ctx.eventTitle })
        .getByRole("button", { name: "Отправить предложение" })
        .click();
      await expect(page).toHaveURL(/\/deals\//, { timeout: 15_000 });
      artistBookingId = page.url().split("/deals/")[1]?.split(/[?#]/)[0] ?? "";
      expect(artistBookingId).toBeTruthy();
      await expect(page.getByText("quote_id:").first()).toBeVisible();
      await page.getByRole("button", { name: "Подтвердить условия" }).click();
      await expect(page.getByText("подтвердил только исполнитель").first()).toBeVisible({ timeout: 10_000 });
      const room = await getJson<{ offer_id: string }>(
        request,
        `/deal-room/${artistBookingId}`,
        ctx.artist.token,
        ctx.artist.orgId,
      );
      artistOfferId = room.offer_id;
    });

    await test.step("venue: заявка и OfferVersion через UI", async () => {
      await injectSession(page, ctx.venue.token, ctx.venue.orgId);
      await page.goto("/cabinet/venue");
      await expect(page.getByRole("heading", { name: "Новые заявки" })).toBeVisible({ timeout: 15_000 });
      await expect(page.getByText(ctx.eventTitle)).toBeVisible();
      await page
        .getByRole("article")
        .filter({ hasText: ctx.eventTitle })
        .getByRole("button", { name: "Отправить предложение" })
        .click();
      await expect(page).toHaveURL(/\/deals\//, { timeout: 15_000 });
      venueBookingId = page.url().split("/deals/")[1]?.split(/[?#]/)[0] ?? "";
      expect(venueBookingId).toBeTruthy();
      await page.getByRole("button", { name: "Подтвердить условия" }).click();
      await expect(page.getByText("подтвердил только исполнитель").first()).toBeVisible({ timeout: 10_000 });
    });

    await test.step("изоляция прав: viewer не может ack", async () => {
      const viewer = await postJson<{ token: string; user_id: string }>(
        request,
        "/auth/register",
        ctx.customer.token,
        {
          email: `e2e-viewer-${Date.now()}@booker.test`,
          password: "password1",
          full_name: "E2E Viewer",
          phone: "+79000000001",
          accept_offer: true,
          accept_privacy: true,
        },
      );
      await postJson(
        request,
        `/orgs/${ctx.customer.orgId}/members`,
        ctx.customer.token,
        { user_id: viewer.user_id, role: "viewer" },
        ctx.customer.orgId,
      );
      const denied = await request.post(`${API_BASE}/offers/${artistOfferId}/ack`, {
        headers: {
          Authorization: `Bearer ${viewer.token}`,
          "Content-Type": "application/json",
          "X-Booker-Org": ctx.customer.orgId,
        },
        data: { side: "customer" },
      });
      expect(denied.status()).toBe(403);
    });

    await test.step("customer: подтверждает обе OfferVersion и удерживает даты", async () => {
      await injectSession(page, ctx.customer.token, ctx.customer.orgId);
      await page.goto("/cabinet/customer");
      await expect(page.getByRole("heading", { name: "Новые предложения" })).toBeVisible({ timeout: 15_000 });
      await expect(page.getByText(ctx.eventTitle).first()).toBeVisible();

      for (const bookingId of [artistBookingId, venueBookingId]) {
        await page.goto(`/deals/${bookingId}`);
        await page.getByRole("button", { name: "Подтвердить условия" }).click();
        await expect(page.getByText("подтверждено обеими сторонами").first()).toBeVisible({ timeout: 10_000 });
        await page.getByRole("button", { name: "Удержать дату" }).click();
        await expect(page.getByText("Дата удерживается").first()).toBeVisible({ timeout: 10_000 });
      }
    });

    await test.step("holds и статусы во всех кабинетах", async () => {
      await injectSession(page, ctx.customer.token, ctx.customer.orgId);
      await page.goto("/cabinet/customer");
      await expect(page.getByRole("heading", { name: "Истекающие hold" })).toBeVisible();

      await injectSession(page, ctx.artist.token, ctx.artist.orgId);
      await page.goto("/cabinet/performer");
      await expect(page.getByRole("heading", { name: "Hold" })).toBeVisible();

      await injectSession(page, ctx.venue.token, ctx.venue.orgId);
      await page.goto("/cabinet/venue");
      await expect(page.getByRole("heading", { name: "Hold" })).toBeVisible();
      await expect(page.getByRole("heading", { name: "Залы" })).toBeVisible();
    });

    await test.step("изоляция бюджета: quote с сервера, не ориентир бюджета события", async () => {
      const room = await getJson<{ quote: { honorarium_rub: number; total_rub: number } }>(
        request,
        `/deal-room/${artistBookingId}`,
        ctx.customer.token,
        ctx.customer.orgId,
      );
      expect(room.quote.honorarium_rub).toBe(100_000);
      expect(room.quote.total_rub).toBeGreaterThanOrEqual(room.quote.honorarium_rub);
      expect(room.quote.total_rub).toBeLessThan(500_000);
    });

    await test.step("отмена artist не ломает venue", async () => {
      const cancelled = await postJson<{ status: string; request_status: string }>(
        request,
        `/bookings/${artistBookingId}/cancel`,
        ctx.customer.token,
        { reason: "E2E: замена DJ" },
        ctx.customer.orgId,
      );
      expect(cancelled.status).toBe("Cancelled");
      expect(cancelled.request_status).toBe("Cancelled");

      const venueRoom = await getJson<{ status: string; hold?: { status: string } }>(
        request,
        `/deal-room/${venueBookingId}`,
        ctx.customer.token,
        ctx.customer.orgId,
      );
      expect(venueRoom.status).not.toBe("Cancelled");
      expect(venueRoom.hold?.status).toBe("active");

      await injectSession(page, ctx.venue.token, ctx.venue.orgId);
      await page.goto("/cabinet/venue");
      await expect(page.getByRole("heading", { name: "Hold" })).toBeVisible();
      await expect(page.getByText(ctx.eventTitle).first()).toBeVisible();

      await injectSession(page, ctx.artist.token, ctx.artist.orgId);
      await page.goto("/cabinet/performer");
      await expect(page.getByText(ctx.eventTitle)).not.toBeVisible();
    });
  });

  test("demo seed accounts доступны", async ({ request }) => {
    test.skip(!(await apiHealth(request)), `API недоступен (${API_BASE})`);
    for (const email of Object.values(DEMO_ACCOUNTS)) {
      const session = await login(request, email);
      expect(session.token).toBeTruthy();
    }
  });
});
