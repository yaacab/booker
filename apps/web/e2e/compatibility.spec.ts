import { expect, test } from "@playwright/test";
import { API_BASE, getJson, injectSession, postJson, register } from "./helpers";

for (const width of [1440, 390]) {
  test.describe(`Compatibility ${width}px`, () => {
    test.use({ viewport: { width, height: 900 } });
    test("E-CUST-04 unknown facts, owner hall edit and missing DJ console", async ({ page, request }, testInfo) => {
      const actor = await register(request, `compat-${width}-${Date.now()}@booker.test`, "Участник");
      const artistOrg = await postJson<{ id: string }>(request, "/orgs", actor.token, { name: "Программа", kind: "artist" });
      const venueOrg = await postJson<{ id: string }>(request, "/orgs", actor.token, { name: "Площадка", kind: "venue" });
      const artist = await postJson<{ id: string }>(request, "/artists", actor.token, { organization_id: artistOrg.id, name: `DJ Совместимость ${width}`, category: "dj" });
      const venue = await postJson<{ id: string; hall_id: string }>(request, "/venues", actor.token, { organization_id: venueOrg.id, name: `Зал Совместимость ${width}`, capacity: 120 });
      const day = new Date(Date.now() + 15 * 86400000).toISOString().slice(0, 10);
      for (const [resource_type, resource_id] of [["artist", artist.id], ["hall", venue.hall_id]]) {
        await postJson(request, "/slots", actor.token, { resource_type, resource_id, starts_at: `${day}T14:00:00Z`, ends_at: `${day}T19:00:00Z` });
      }
      const presentation = await getJson<{ version: number; data: object }>(request, `/artists/${artist.id}/presentation`, actor.token);
      const headers = { Authorization: `Bearer ${actor.token}` };
      const put = await request.put(`${API_BASE}/artists/${artist.id}/presentation`, { headers, data: { ...presentation.data, expected_version: presentation.version, technical: { stage_area_m2: 12, power_kw: 3, basic_sound: true, microphones: 2, setup_minutes: 30, teardown_minutes: 20, required_equipment: ["CDJ-3000"], supplied_equipment: [] } } });
      expect(put.ok()).toBe(true);
      await injectSession(page, actor.token, venueOrg.id);
      async function check() {
        await page.goto(`/compatibility?artist=${artist.id}&venue=${venue.id}`);
        await page.getByLabel("Начало, по Москве", { exact: true }).fill(`${day}T18:00`);
        await page.getByLabel("Окончание, по Москве", { exact: true }).fill(`${day}T21:00`);
        await page.getByLabel("Гостей", { exact: true }).fill("100");
        await page.getByRole("button", { name: "Проверить совместимость", exact: true }).click();
      }
      await check();
      await expect(page.getByRole("region", { name: "Результат совместимости" }).getByText("Недостаточно данных", { exact: true }).first()).toBeVisible();
      await page.goto("/cabinet/venue/technical");
      const form = page.getByRole("form", { name: "Оснащение зала" });
      await form.getByLabel("Площадь сцены, м²", { exact: true }).fill("20");
      await form.getByLabel("Доступная мощность, кВт", { exact: true }).fill("5");
      await form.getByLabel("Микрофоны, шт.", { exact: true }).fill("3");
      await form.getByRole("combobox", { name: "Базовый звук", exact: true }).selectOption("yes");
      await form.getByLabel("Оборудование — точные модели по одной на строке", { exact: true }).fill("CDJ-3000");
      await form.getByLabel("Дополнительных ограничений нет", { exact: true }).check();
      await form.getByRole("button", { name: "Сохранить параметры зала", exact: true }).click();
      await expect(page.getByRole("status").filter({ hasText: "Параметры зала сохранены" })).toBeVisible();
      await check();
      await expect(page.getByRole("heading", { name: "Совместимость: подходит", exact: true })).toBeVisible();
      await expect(page.getByText("100%", { exact: false }).first()).toBeVisible();
      const saved = await getJson<{ version: number; data: object }>(request, `/halls/${venue.hall_id}/technical`, actor.token);
      const changed = await request.put(`${API_BASE}/halls/${venue.hall_id}/technical`, { headers, data: { ...saved.data, equipment: [], expected_version: saved.version } });
      expect(changed.ok()).toBe(true);
      await page.getByRole("button", { name: "Проверить совместимость", exact: true }).click();
      await expect(page.getByRole("heading", { name: "Совместимость: есть несоответствие", exact: true })).toBeVisible();
      await expect(page.getByText("Не хватает: CDJ-3000", { exact: true })).toBeVisible();
      await expect(page.getByRole("heading", { name: "Что нужно согласовать", exact: true })).toBeVisible();
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
      await page.screenshot({ path: testInfo.outputPath("compatibility.png"), fullPage: true });
    });
  });
}
