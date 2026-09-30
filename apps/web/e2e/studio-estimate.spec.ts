import { expect, test } from "@playwright/test";
import { API_BASE, postJson, register } from "./helpers";

const SAFE_SERVICE_ERROR = "Сервис временно недоступен. Попробуйте ещё раз позже.";
for (const width of [1440, 390]) {
  test.describe(`Server studio estimate ${width}px`, () => {
    test.use({ viewport: { width, height: 900 } });
    test("published package range, partial data and network retry", async ({ page, request }, testInfo) => {
      const actor = await register(request, `estimate-${width}-${Date.now()}@booker.test`, "Артист");
      const org = await postJson<{ id: string }>(request, "/orgs", actor.token, { name: "Стоимость пакетов", kind: "artist" });
      const artist = await postJson<{ id: string }>(request, "/artists", actor.token, { organization_id: org.id, name: "DJ с тарифами" });
      const missing = await postJson<{ id: string }>(request, "/artists", actor.token, { organization_id: org.id, name: "Ведущий без тарифа", category: "host" });
      for (const honorarium_rub of [60000, 90000]) await postJson(request, `/artists/${artist.id}/tariffs`, actor.token, { title: "Пакет", honorarium_rub, hours: 2 });
      await page.addInitScript(({ ids }) => {
        localStorage.setItem("booker.eventStudioMapDraft", JSON.stringify({ draft: { title: "Серверный ориентир", kind: "Корпоратив", city: "Москва", date: "", startsAt: "17:00", endsAt: "23:30", guests: 100, talentIds: ids, requirements: [], version: 1 }, savedAt: new Date().toISOString() }));
      }, { ids: [artist.id, missing.id] });
      let outage = true;
      await page.route(`${API_BASE}/event-studio/estimate`, async (route) => {
        if (outage) { await route.fulfill({ status: 503, contentType: "application/json", body: JSON.stringify({ detail: "Расчёт временно недоступен" }) }); }
        else await route.continue();
      });
      await page.goto("/events/new?event_studio_map_v1=1");
      const estimate = page.getByRole("region", { name: "Ориентир бюджета" });
      await expect(estimate.getByRole("alert")).toHaveText(SAFE_SERVICE_ERROR);
      outage = false;
      await estimate.getByRole("button", { name: "Повторить расчёт" }).click();
      await expect(estimate).toContainText(/60\s?000 ₽ — 90\s?000 ₽/);
      await expect(estimate).toContainText("Только известная часть состава.");
      await expect(estimate).toContainText("Стоимость указана у 1 из 2 участников.");
      await postJson(request, `/artists/${missing.id}/tariffs`, actor.token, { title: "Программа", honorarium_rub: 30000, hours: 2 });
      await page.reload();
      await expect(estimate).toContainText(/90\s?000 ₽ — 120\s?000 ₽/);
      await expect(estimate).toContainText("Стоимость указана у 2 из 2 участников.");
      await expect(estimate).not.toContainText("Только известная часть");
      await estimate.getByText("Как рассчитано", { exact: true }).click();
      await expect(estimate).toContainText("без сервисного сбора заказчика");
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
      await estimate.screenshot({ path: testInfo.outputPath("estimate.png") });
    });
  });
}
