import { expect, test } from "@playwright/test";
import { API_BASE, getJson, injectSession, postJson, register } from "./helpers";

for (const width of [1440, 390]) {
  test.describe(`Replacement ${width}px`, () => {
    test.use({ viewport: { width, height: 900 } });
    test("E-REPLACE-01 available replacement, stale calendar and safe retry", async ({ page, request }, testInfo) => {
      const suffix = `${width}-${Date.now()}`;
      const customer = await register(request, `replace-c-${suffix}@booker.test`, "Заказчик");
      const supplier = await register(request, `replace-s-${suffix}@booker.test`, "Артист");
      const org = await postJson<{ id: string }>(request, "/orgs", customer.token, { name: "Организаторы", kind: "customer" });
      const supply = await postJson<{ id: string }>(request, "/orgs", supplier.token, { name: "Музыка", kind: "artist" });
      const city = `Город замен ${suffix}`;
      const day = new Date(Date.now() + 20 * 86400000).toISOString().slice(0, 10);
      const artists: { id: string; name: string; slot: string }[] = [];
      for (const name of ["DJ Отменён", "DJ Свободен", "DJ Короткое окно", "DJ Уже занят"]) {
        const artist = await postJson<{ id: string }>(request, "/artists", supplier.token, { organization_id: supply.id, name, category: "dj", city });
        const slot = await postJson<{ id: string }>(request, "/slots", supplier.token, { resource_type: "artist", resource_id: artist.id, starts_at: `${day}T14:00:00Z`, ends_at: `${day}T${name === "DJ Короткое окно" ? "17" : "19"}:00:00Z` });
        artists.push({ ...artist, name, slot: slot.id });
      }
      const patchSlot = async (resource_id: string, status: string) => {
        const data = { organization_id: supply.id, resource_type: "artist", resource_id };
        if (status === "busy") await postJson(request, "/calendar/vacation", supplier.token, { ...data, starts_at: `${day}T15:00:00Z`, ends_at: `${day}T18:00:00Z` });
        else { const response = await request.delete(`${API_BASE}/calendar/vacation`, { headers: { Authorization: `Bearer ${supplier.token}` }, data }); expect(response.ok(), await response.text()).toBeTruthy(); }
      };
      await patchSlot(artists[3].id, "busy");
      const event = await postJson<{ id: string; requirements: { id: string }[] }>(request, "/events", customer.token, { organization_id: org.id, title: "Вечер с музыкой", city, event_date: `${day}T15:00:00Z`, ends_at: `${day}T18:00:00Z`, requirements: [{ category_code: "dj" }] });
      const req = await postJson<{ id: string }>(request, `/events/${event.id}/requests`, customer.token, { resource_type: "artist", resource_id: artists[0].id, requirement_id: event.requirements[0].id });
      const offer = await postJson<{ booking_id: string }>(request, `/requests/${req.id}/offers`, supplier.token, { slot_id: artists[0].slot, honorarium_rub: 80000 });
      await postJson(request, `/bookings/${offer.booking_id}/cancel`, supplier.token, {});
      await injectSession(page, customer.token, org.id);
      await page.goto("/notifications");
      const notification = page.getByRole("article").filter({ has: page.getByRole("heading", { name: "Проверьте замену участника", exact: true }) });
      await expect(notification).toContainText("не гарантируется");
      await expect(notification.getByRole("link", { name: "Открыть", exact: true })).toHaveAttribute("href", `/events/${event.id}#event-roles`);
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
      await page.screenshot({ path: testInfo.outputPath("replacement-notification.png") });
      await notification.getByRole("link", { name: "Открыть", exact: true }).click();
      const panel = page.getByRole("article", { name: "Замена: DJ", exact: true });
      await panel.getByRole("button", { name: "Подобрать замену", exact: true }).click();
      await expect(panel.getByRole("link", { name: "DJ Свободен", exact: true })).toBeVisible();
      await expect(panel.getByRole("link", { name: "DJ Короткое окно", exact: true })).toHaveCount(0);
      await expect(panel.getByRole("link", { name: "DJ Уже занят", exact: true })).toHaveCount(0);
      await expect(panel.getByRole("link", { name: "DJ Отменён", exact: true })).toHaveCount(0);
      await panel.getByText("Что нужно уточнить", { exact: false }).click();
      await expect(panel).toContainText("Площадка не выбрана");
      await patchSlot(artists[1].id, "busy");
      await panel.getByRole("button", { name: "Запросить новое предложение", exact: true }).click();
      await expect(panel.getByRole("alert")).toContainText("больше не доступен");
      await panel.getByRole("button", { name: "Обновить доступность" }).click();
      await expect(panel).toContainText("Свободных вариантов с подходящими условиями пока нет");
      await patchSlot(artists[1].id, "open");
      await panel.getByRole("button", { name: "Обновить доступность" }).click();
      await expect(panel.getByRole("link", { name: "DJ Свободен", exact: true })).toBeVisible();
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
      await panel.evaluate(el => window.scrollBy({ top: el.getBoundingClientRect().top - (document.querySelector("header.top")?.getBoundingClientRect().height || 0) - 16, behavior: "instant" }));
      await page.screenshot({ path: testInfo.outputPath("replacement.png") });
      let lose = true;
      await page.route(`${API_BASE}/events/${event.id}/requirements/${event.requirements[0].id}/replacement-requests`, async route => { if (lose) { lose = false; expect((await route.fetch()).status()).toBe(200); await route.abort("failed"); } else await route.continue(); });
      await panel.getByRole("button", { name: "Запросить новое предложение", exact: true }).click();
      await expect(panel.getByRole("alert")).toBeVisible();
      await panel.getByRole("button", { name: "Запросить новое предложение", exact: true }).click();
      await expect(panel).toContainText("Запрос отправлен: DJ Свободен");
      const result = await getJson<{ requests: { resource_id: string; booking_id: string | null }[] }>(request, `/events/${event.id}`, customer.token);
      expect(result.requests).toHaveLength(2);
      const replacement = result.requests.find(r => r.resource_id === artists[1].id); expect(replacement).toBeTruthy(); expect(replacement?.booking_id).toBeNull();
    });
  });
}
