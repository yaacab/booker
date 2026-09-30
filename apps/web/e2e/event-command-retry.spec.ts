import { expect, test } from "@playwright/test";
import { API_BASE, getJson, injectSession, postJson, register } from "./helpers";

for (const width of [1440, 390]) {
  test.describe(`Event command retry ${width}px`, () => {
    test.use({ viewport: { width, height: 900 } });
    test("lost second request response resumes one event and one request per participant", async ({ page, request }) => {
      const actor = await register(request, `event-retry-${width}-${Date.now()}@booker.test`, "Организатор");
      const org = await postJson<{ id: string }>(request, "/orgs", actor.token, { name: "События", kind: "customer" });
      const supplier = await postJson<{ id: string }>(request, "/orgs", actor.token, { name: "Исполнители", kind: "artist" });
      const artists: { id: string }[] = [];
      for (const category of ["dj", "host"]) artists.push(await postJson<{ id: string }>(request, "/artists", actor.token, { organization_id: supplier.id, name: `Участник ${category}`, category }));
      const day = new Date(Date.now() + 18 * 86400000).toISOString().slice(0, 10);
      await page.addInitScript(({ ids, day }) => {
        localStorage.setItem("booker.eventStudioMapDraft", JSON.stringify({ draft: { title: "Ночной корпоратив", kind: "Корпоратив", city: "Москва", date: day, startsAt: "18:00", endsAt: "02:00", endsNextDay: true, guests: 100, budgetRub: 400000, talentIds: ids, requirements: [], version: 1 }, savedAt: new Date().toISOString() }));
        // A legacy browser cache must not replace the server's authorization/command receipts.
        sessionStorage.setItem("booker.eventStudioSubmitKey:result", "stale-browser-result");
      }, { ids: artists.map((a) => a.id), day });
      await injectSession(page, actor.token, org.id);
      let fail = true;
      await page.route(`${API_BASE}/events/*/requests`, async (route) => {
        if (route.request().method() === "POST" && route.request().postDataJSON().resource_id === artists[1].id && fail) {
          fail = false;
          const accepted = await route.fetch();
          expect(accepted.ok()).toBe(true);
          await route.fulfill({ status: 503, contentType: "application/json", body: JSON.stringify({ detail: "Ответ потерян после сохранения заявки" }) });
        } else await route.continue();
      });
      await page.goto("/events/new?event_studio_map_v1=1");
      await page.getByRole("button", { name: "Проверка", exact: false }).click();
      await page.getByRole("button", { name: "Продолжить", exact: false }).click();
      await expect(page.getByRole("alert").filter({ hasText: "Сервис временно недоступен" })).toBeVisible();
      await expect(page.getByText("Ответ потерян после сохранения заявки")).toHaveCount(0);
      await page.getByRole("button", { name: "Продолжить", exact: false }).click();
      await expect(page).toHaveURL(/\/events\/[0-9a-f-]{36}$/);
      await expect(page.getByText(/Ваш бюджет: 400\s?000 ₽/)).toBeVisible();
      const events = await getJson<{ items: { id: string }[] }>(request, `/events?organization_id=${org.id}`, actor.token);
      expect(events.items).toHaveLength(1);
      const event = await getJson<{ ends_at: string; event_date: string; event_type: string; budget_rub: number; requirements: object[]; requests: { resource_id: string; booking_id: string | null }[] }>(request, `/events/${events.items[0].id}`, actor.token);
      expect(event.event_type).toBe("Корпоратив"); expect(event.budget_rub).toBe(400000);
      expect(new Date(event.ends_at).getTime() - new Date(event.event_date).getTime()).toBe(8 * 3600000);
      expect(event.requirements).toHaveLength(2); expect(event.requests).toHaveLength(2);
      expect(new Set(event.requests.map((r) => r.resource_id)).size).toBe(2);
      expect(event.requests.every((r) => r.booking_id === null)).toBe(true);
    });
  });
}

test("classic studio preserves declared budget and explicit end and opens created event", async ({ page, request }) => {
  const actor = await register(request, `classic-create-${Date.now()}@booker.test`, "Организатор");
  const org = await postJson<{ id: string }>(request, "/orgs", actor.token, { name: "Событие", kind: "customer" });
  const day = new Date(Date.now() + 12 * 86400000).toISOString().slice(0, 10);
  await page.addInitScript(({ day }) => {
    localStorage.setItem("booker.eventDraft", JSON.stringify({ draft: { what: "Корпоратив", city: "Москва", date: `${day}T18:00`, endsAt: `${day}T23:00`, guests: "80", artist: "dj", roles: ["dj"], roleQty: { dj: 1 }, venue: "need", tech: "unknown", budget: "250000" }, unknown: { tech: true }, step: 7 }));
  }, { day });
  await injectSession(page, actor.token, org.id);
  await page.goto("/events/new");
  await page.getByRole("button", { name: "Сохранить и в сделки" }).click();
  await expect(page).toHaveURL(/\/events\/[0-9a-f-]{36}$/);
  const id = page.url().split("/").pop();
  const event = await getJson<{ budget_rub: number; event_type: string; ends_at: string }>(request, `/events/${id}`, actor.token);
  expect(event.budget_rub).toBe(250000); expect(event.event_type).toBe("Корпоратив");
  expect(new Date(event.ends_at).toISOString()).toBe(`${day}T20:00:00.000Z`);
});
