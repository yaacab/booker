import { expect, test } from "@playwright/test";
import { API_BASE, getJson, injectSession, postJson, register } from "./helpers";

type Plan = { revision: number; context_token: string; saved_selections: { resource_id: string; hall_id: string | null }[]; requirements: { id: string; category_code: string }[] };
for (const width of [1440, 390]) {
  test.describe(`Compare V2 ${width}px`, () => {
    test.use({ viewport: { width, height: 900 } });
    test("E-CUST-02 factual artists and halls, retry and explicit preliminary selection", async ({ page, request }, testInfo) => {
      const actor = await register(request, `compare-${width}-${Date.now()}@booker.test`, "Организатор");
      const city = `Город сравнения ${width}-${Date.now()}`;
      const customer = await postJson<{ id: string }>(request, "/orgs", actor.token, { name: "Заказчик", kind: "customer" });
      const supply = await postJson<{ id: string }>(request, "/orgs", actor.token, { name: "Артисты", kind: "artist" });
      const venueOrg = await postJson<{ id: string }>(request, "/orgs", actor.token, { name: "Площадки", kind: "venue" });
      const headers = { Authorization: `Bearer ${actor.token}` };
      const day = new Date(Date.now() + 22 * 86400000).toISOString().slice(0, 10);
      const event = await postJson<{ id: string }>(request, "/events", actor.token, { organization_id: customer.id, title: "Вечер команды", city, event_date: `${day}T15:00:00Z`, ends_at: `${day}T18:00:00Z`, guest_count: 100, requirements: [{ category_code: "dj" }, { category_code: "venue" }] });
      const artists: string[] = [];
      for (const [name, price, detailed] of [["DJ Базовый", 60000, false], ["DJ С программой", 90000, true]] as const) {
        const artist = await postJson<{ id: string }>(request, "/artists", actor.token, { organization_id: supply.id, name, city, category: "dj" }); artists.push(artist.id);
        await postJson(request, `/artists/${artist.id}/tariffs`, actor.token, { title: "Три часа музыки", honorarium_rub: price, hours: 3 });
        await postJson(request, "/slots", actor.token, { resource_type: "artist", resource_id: artist.id, starts_at: `${day}T14:00:00Z`, ends_at: `${day}T19:00:00Z` });
        if (detailed) {
          const old = await getJson<{ version: number; data: object }>(request, `/artists/${artist.id}/presentation`, actor.token);
          const result = await request.put(`${API_BASE}/artists/${artist.id}/presentation`, { headers, data: { ...old.data, expected_version: old.version, format: "Корпоратив", lineup: "Один исполнитель", technical: { stage_area_m2: 12, power_kw: 3, basic_sound: true, microphones: 2, setup_minutes: 30, teardown_minutes: 20, required_equipment: ["CDJ"], supplied_equipment: [] } } }); expect(result.ok()).toBe(true);
        }
      }
      const venues: { id: string; hall_id: string }[] = [];
      for (const [name, capacity] of [["Просторный зал", 150], ["Камерный зал", 60]] as const) {
        const venue = await postJson<{ id: string; hall_id: string }>(request, "/venues", actor.token, { organization_id: venueOrg.id, name, city, capacity }); venues.push(venue);
        await postJson(request, `/venues/${venue.id}/tariffs`, actor.token, { title: "Аренда вечера", honorarium_rub: 100000 });
        await postJson(request, "/slots", actor.token, { resource_type: "hall", resource_id: venue.hall_id, starts_at: `${day}T14:00:00Z`, ends_at: `${day}T19:00:00Z` });
        const result = await request.put(`${API_BASE}/halls/${venue.hall_id}/technical`, { headers, data: { expected_version: 0, capacity, stage_area_m2: 20, power_kw: 5, basic_sound: true, microphones: 3, equipment: ["CDJ"], restrictions: "" } }); expect(result.ok()).toBe(true);
      }
      await injectSession(page, actor.token, customer.id);
      let fail = true;
      await page.route(`${API_BASE}/compare?*`, async (route) => { if (fail) { fail = false; await route.fulfill({ status: 503, contentType: "application/json", body: JSON.stringify({ detail: "Сравнение временно недоступно" }) }); } else await route.continue(); });
      await page.goto(`/compare?type=artist&ids=${artists.join(",")}`);
      await expect(page.locator("main").getByRole("alert")).toContainText("Сравнение временно недоступно");
      await page.getByRole("button", { name: "Обновить сравнение", exact: true }).click();
      const basic = page.getByRole("article", { name: "Сравнение: DJ Базовый", exact: true });
      const detailed = page.getByRole("article", { name: "Сравнение: DJ С программой", exact: true });
      await expect(basic).toContainText("Пока недостаточно отзывов");
      await expect(detailed).toContainText(/90\s?000 ₽/);
      await expect(detailed).toContainText("Корпоратив");
      await expect(detailed.getByRole("button", { name: "Добавить в событие" })).toBeDisabled();
      await page.getByRole("combobox", { name: "Событие", exact: true }).selectOption(event.id);
      await expect(page.getByRole("combobox", { name: "Позиция для добавления", exact: true })).toBeEnabled();
      const plan = await getJson<Plan>(request, `/events/${event.id}/matching`, actor.token);
      const dj = plan.requirements.find((r) => r.category_code === "dj")!;
      const hallRole = plan.requirements.find((r) => r.category_code === "venue")!;
      await page.getByRole("combobox", { name: "Площадка для проверки райдера", exact: true }).selectOption(venues[0].id);
      await expect(page.getByRole("combobox", { name: "Зал для проверки", exact: true })).toHaveValue(venues[0].hall_id);
      await expect(detailed.locator(".compare-fit")).toContainText("Подходит");
      await page.getByRole("combobox", { name: "Позиция для добавления", exact: true }).selectOption(`${dj.id}:0`);
      // Another tab changes the plan after this comparison has read its revision.
      const concurrent = await request.put(`${API_BASE}/events/${event.id}/plan`, { headers, data: { expected_revision: plan.revision, expected_context: plan.context_token, selections: [{ requirement_id: dj.id, position: 0, resource_type: "artist", resource_id: artists[0], hall_id: null }] } });
      expect(concurrent.ok()).toBe(true);
      await detailed.getByRole("button", { name: "Добавить в событие" }).click();
      await expect(page.locator("main").getByRole("alert")).toContainText("Предварительный состав уже изменён");
      expect((await getJson<Plan>(request, `/events/${event.id}/matching`, actor.token)).saved_selections.map((s) => s.resource_id)).toEqual([artists[0]]);
      await page.getByRole("button", { name: "Обновить сравнение", exact: true }).click();
      await page.getByRole("combobox", { name: "Позиция для добавления", exact: true }).selectOption(`${dj.id}:0`);
      await detailed.getByRole("button", { name: "Добавить в событие" }).click();
      await expect(page.getByRole("status").filter({ hasText: "добавлено в предварительный состав" })).toBeVisible();
      expect((await getJson<Plan>(request, `/events/${event.id}/matching`, actor.token)).saved_selections.map((s) => s.resource_id)).toEqual([artists[1]]);
      expect((await getJson<{ requests: object[] }>(request, `/events/${event.id}`, actor.token)).requests).toHaveLength(0);
      await page.locator(".comparison-grid").evaluate((el) => { window.scrollBy({ top: el.getBoundingClientRect().top - (document.querySelector("header.top")?.getBoundingClientRect().height || 0) - 16, behavior: "instant" }); });
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
      await page.screenshot({ path: testInfo.outputPath("artists-viewport.png") });
      // Public profiles expose the same local shortlist flow for venues as for artists.
      for (const venue of venues) { await page.goto(`/venues/${venue.id}`); await page.getByRole("button", { name: "Сравнить", exact: true }).click(); }
      await page.getByRole("link", { name: "Сравнение (2)", exact: true }).click();
      await expect(page.getByRole("heading", { name: "Сравнение площадок", exact: true })).toBeVisible();
      await page.getByRole("combobox", { name: "Событие", exact: true }).selectOption(event.id);
      await page.getByRole("combobox", { name: "Артист для проверки залов", exact: true }).selectOption(artists[1]);
      const spacious = page.getByRole("article", { name: "Сравнение: Просторный зал", exact: true });
      const small = page.getByRole("article", { name: "Сравнение: Камерный зал", exact: true });
      await small.locator("details").last().locator("summary").click();
      await expect(small).toContainText("Вместимости недостаточно");
      await spacious.locator("details").last().locator("summary").click();
      await expect(spacious).toContainText("CDJ");
      await expect(spacious.locator(".compare-fit")).toContainText("Подходит");
      await page.getByRole("combobox", { name: "Позиция для добавления", exact: true }).selectOption(`${hallRole.id}:0`);
      await spacious.getByRole("button", { name: "Добавить в событие" }).click();
      await expect(page.getByRole("status").filter({ hasText: "добавлено в предварительный состав" })).toBeVisible();
      const saved = await getJson<Plan>(request, `/events/${event.id}/matching`, actor.token);
      expect(saved.saved_selections.map((s) => s.resource_id).sort()).toEqual([artists[1], venues[0].id].sort());
      expect(saved.saved_selections.find((s) => s.resource_id === venues[0].id)?.hall_id).toBe(venues[0].hall_id);
      expect((await getJson<{ requests: object[] }>(request, `/events/${event.id}`, actor.token)).requests).toHaveLength(0);
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
      await spacious.evaluate((el) => { window.scrollBy({ top: el.getBoundingClientRect().top - (document.querySelector("header.top")?.getBoundingClientRect().height || 0) - 16, behavior: "instant" }); });
      await page.screenshot({ path: testInfo.outputPath("venues-viewport.png") });
      await page.getByRole("button", { name: "Сбросить подборку", exact: true }).click();
      await expect(page.getByText("Выберите от двух до четырёх профилей:", { exact: false })).toBeVisible();
      expect(await page.evaluate(() => JSON.parse(localStorage.getItem("booker.venue-compare") || "[]"))).toEqual([]);
    });
  });
}
