import { expect, test } from "@playwright/test";
import { API_BASE, getJson, injectSession, postJson, register } from "./helpers";

for (const width of [1440, 390]) {
  test.describe(`Smart matching ${width}px`, () => {
    test.use({ viewport: { width, height: 900 } });
    test("E-CUST-01 studio produces three variants, replacement and explicit requests", async ({ page, request }, testInfo) => {
      const actor = await register(request, `matching-${width}-${Date.now()}@booker.test`, "Организатор");
      const city = `Город подбора ${width}-${Date.now()}`;
      const customer = await postJson<{ id: string }>(request, "/orgs", actor.token, { name: "Организатор", kind: "customer" });
      const supply = await postJson<{ id: string }>(request, "/orgs", actor.token, { name: "Артисты", kind: "artist" });
      const venueOrg = await postJson<{ id: string }>(request, "/orgs", actor.token, { name: "Залы", kind: "venue" });
      const day = new Date(Date.now() + 20 * 86400000).toISOString().slice(0, 10);
      const ids: string[] = [];
      const tech = { stage_area_m2: 12, power_kw: 3, basic_sound: true, microphones: 2, setup_minutes: 30, teardown_minutes: 20, required_equipment: ["CDJ"], supplied_equipment: [] };
      for (const [index, name, honorarium] of [[0, "Доступный DJ", 60000], [1, "DJ с указанной техникой", 90000], [2, "DJ с подробной программой", 120000]] as const) {
        const artist = await postJson<{ id: string }>(request, "/artists", actor.token, { organization_id: supply.id, name, city, category: "dj" }); ids.push(artist.id);
        await postJson(request, `/artists/${artist.id}/tariffs`, actor.token, { title: "Пакет", honorarium_rub: honorarium, hours: 3 });
        await postJson(request, "/slots", actor.token, { resource_type: "artist", resource_id: artist.id, starts_at: `${day}T14:00:00Z`, ends_at: `${day}T19:00:00Z` });
        if (index) {
          const old = await getJson<{ version: number; data: object }>(request, `/artists/${artist.id}/presentation`, actor.token);
          const result = await request.put(`${API_BASE}/artists/${artist.id}/presentation`, { headers: { Authorization: `Bearer ${actor.token}` }, data: { ...old.data, expected_version: old.version, technical: tech, ...(index === 2 ? { format: "Корпоратив", lineup: "Два участника", program: "Подробная программа вечера" } : {}) } }); expect(result.ok()).toBe(true);
        }
      }
      const venue = await postJson<{ id: string; hall_id: string }>(request, "/venues", actor.token, { organization_id: venueOrg.id, name: "Зал для состава", city, capacity: 150 });
      await postJson(request, `/venues/${venue.id}/tariffs`, actor.token, { title: "Аренда", honorarium_rub: 100000 });
      await postJson(request, "/slots", actor.token, { resource_type: "hall", resource_id: venue.hall_id, starts_at: `${day}T14:00:00Z`, ends_at: `${day}T19:00:00Z` });
      const technical = await request.put(`${API_BASE}/halls/${venue.hall_id}/technical`, { headers: { Authorization: `Bearer ${actor.token}` }, data: { expected_version: 0, capacity: 150, stage_area_m2: 20, power_kw: 5, basic_sound: true, microphones: 3, equipment: ["CDJ"], restrictions: "" } }); expect(technical.ok()).toBe(true);
      await page.addInitScript(({ day, city }) => { localStorage.setItem("booker.eventDraft", JSON.stringify({ draft: { what: "Корпоратив", city, date: `${day}T18:00`, endsAt: `${day}T21:00`, guests: "100", artist: "dj", roles: ["dj"], roleQty: { dj: 1 }, venue: "need", tech: "unknown", budget: "300000" }, unknown: { tech: true }, step: 7 })); }, { day, city });
      await injectSession(page, actor.token, customer.id);
      let fail = true;
      await page.route(`${API_BASE}/events/*/matching`, async (route) => { if (fail) { fail = false; await route.fulfill({ status: 503, contentType: "application/json", body: JSON.stringify({ detail: "Подбор временно недоступен" }) }); } else await route.continue(); });
      await page.goto("/events/new"); await page.getByRole("button", { name: "Сохранить и в сделки" }).click();
      await expect(page).toHaveURL(/\/events\/[0-9a-f-]{36}$/);
      const matching = page.getByRole("region", { name: "Подбор состава" });
      await expect(matching.getByRole("alert")).toContainText("Подбор временно недоступен");
      await matching.getByRole("button", { name: "Обновить подбор", exact: true }).click();
      for (const name of ["Экономный", "Оптимальный", "Расширенный"]) await expect(matching.getByRole("heading", { name, exact: true })).toBeVisible();
      await matching.locator(".matching-variants").evaluate((element) => { const header = document.querySelector("header.top"); window.scrollBy({ top: element.getBoundingClientRect().top - (header?.getBoundingClientRect().height || 0) - 16, behavior: "instant" }); });
      await page.screenshot({ path: testInfo.outputPath("variants-viewport.png") });
      await matching.getByRole("button", { name: "Выбрать «Оптимальный»", exact: true }).click();
      const current = matching.getByRole("region", { name: "Предварительный состав" });
      await expect(current.getByRole("link", { name: "DJ с указанной техникой", exact: true })).toBeVisible();
      const eventId = page.url().split("/").pop();
      let event = await getJson<{ requests: object[] }>(request, `/events/${eventId}`, actor.token); expect(event.requests).toHaveLength(0);
      await current.getByRole("combobox", { name: "DJ", exact: true }).selectOption(`artist:${ids[2]}:`);
      await expect(current.getByRole("button", { name: "Отправить заявки выбранным участникам" })).toBeDisabled();
      await current.getByRole("button", { name: "Сохранить изменения состава" }).click();
      await expect(current.getByRole("link", { name: "DJ с подробной программой", exact: true })).toBeVisible();
      await expect(current).toContainText(/220\s?000 ₽/);
      await current.getByRole("button", { name: "Отправить заявки выбранным участникам" }).click();
      await expect(matching.getByRole("status")).toContainText("Заявки выбранным участникам отправлены");
      await current.getByRole("button", { name: "Отправить заявки выбранным участникам" }).click();
      event = await getJson<{ requests: object[] }>(request, `/events/${eventId}`, actor.token); expect(event.requests).toHaveLength(2);
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
      await expect(current.getByRole("button", { name: "Отправить заявки выбранным участникам" })).toBeEnabled();
      await current.evaluate((element) => { const header = document.querySelector("header.top"); window.scrollBy({ top: element.getBoundingClientRect().top - (header?.getBoundingClientRect().height || 0) - 16, behavior: "instant" }); });
      await page.screenshot({ path: testInfo.outputPath("matching-viewport.png") });
    });
  });
}
