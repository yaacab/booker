import { execFileSync } from "node:child_process";
import { expect, test } from "@playwright/test";
import { API_BASE, getJson, injectSession, postJson, register } from "./helpers";

const SAFE_SERVICE_ERROR = "Сервис временно недоступен. Попробуйте ещё раз позже.";
function publishVenueFixture(id: string) {
  if (!process.env.BOOKER_DATABASE_URL?.startsWith("sqlite:////tmp/")) throw new Error("Venue fixture requires disposable SQLite in /tmp");
  execFileSync(process.env.BOOKER_PYTHON_BIN || "python3", ["-c", `
import sys
from types import SimpleNamespace
from sqlalchemy.orm import sessionmaker
from booker_api.db import make_engine
from tests.conftest import activate_venue
SessionLocal = sessionmaker(bind=make_engine(sys.argv[1]), autoflush=False, autocommit=False, future=True)
client = SimpleNamespace(app=SimpleNamespace(state=SimpleNamespace(SessionLocal=SessionLocal)))
activate_venue(client, sys.argv[2])
`, process.env.BOOKER_DATABASE_URL, id], { cwd: "../api", env: process.env });
}
for (const width of [1440, 390]) {
  test.describe(`Event readiness ${width}px`, () => {
    test.use({ viewport: { width, height: 900 } });
    test("E-CUST-05 actual preparation, customer next action and technical blocker", async ({ page, request }, testInfo) => {
      const suffix = `${width}-${Date.now()}`;
      const customer = await register(request, `ready-c-${suffix}@booker.test`, "Организатор");
      const supplier = await register(request, `ready-s-${suffix}@booker.test`, "Исполнитель");
      const org = await postJson<{ id: string }>(request, "/orgs", customer.token, { name: "Организатор", kind: "customer" });
      const supply = await postJson<{ id: string }>(request, "/orgs", supplier.token, { name: "Артисты", kind: "artist" });
      const venueOrg = await postJson<{ id: string }>(request, "/orgs", supplier.token, { name: "Площадки", kind: "venue" });
      const city = `Город готовности ${suffix}`;
      const startMs = Date.now() + 25 * 86400000;
      const start = new Date(startMs).toISOString(), end = new Date(startMs + 3 * 3600000).toISOString();
      const event = await postJson<{ id: string; requirements: { id: string }[] }>(request, "/events", customer.token, { organization_id: org.id, title: "Корпоратив с проверками", city, event_date: start, guest_count: 100, requirements: [{ category_code: "dj" }, { category_code: "venue" }] });
      const artist = await postJson<{ id: string }>(request, "/artists", supplier.token, { organization_id: supply.id, name: "DJ для события", city, category: "dj" });
      const presentation = await getJson<{ version: number; data: object }>(request, `/artists/${artist.id}/presentation`, supplier.token);
      const technical = { stage_area_m2: 12, power_kw: 3, basic_sound: true, microphones: 2, setup_minutes: 30, teardown_minutes: 20, required_equipment: ["CDJ"], supplied_equipment: [] };
      expect((await request.put(`${API_BASE}/artists/${artist.id}/presentation`, { headers: { Authorization: `Bearer ${supplier.token}` }, data: { ...presentation.data, expected_version: presentation.version, technical } })).ok()).toBe(true);
      const venue = await postJson<{ id: string; hall_id: string }>(request, "/venues", supplier.token, { organization_id: venueOrg.id, name: "Зал события", city, capacity: 150 });
      const hallFacts = { capacity: 150, stage_area_m2: 20, power_kw: 5, basic_sound: true, microphones: 3, equipment: ["CDJ"], restrictions: "" };
      expect((await request.put(`${API_BASE}/halls/${venue.hall_id}/technical`, { headers: { Authorization: `Bearer ${supplier.token}` }, data: { ...hallFacts, expected_version: 0 } })).ok()).toBe(true);
      publishVenueFixture(venue.id);
      await injectSession(page, customer.token, org.id);
      let outage = true;
      await page.route(`${API_BASE}/events/${event.id}/readiness`, async (route) => {
        if (outage) { await route.fulfill({ status: 503, contentType: "application/json", body: JSON.stringify({ detail: "Проверки временно недоступны" }) }); }
        else await route.continue();
      });
      await page.goto(`/events/${event.id}`);
      const panel = page.getByRole("region", { name: "Готовность события", exact: true });
      await expect(panel.getByRole("alert")).toHaveText(SAFE_SERVICE_ERROR);
      outage = false;
      await panel.getByRole("button", { name: "Обновить готовность" }).click();
      await expect(panel).toContainText("0 из 2 обязательных позиций подтверждено сделками");
      await expect(panel.getByRole("heading", { name: "Уточнить окно события", exact: true })).toBeVisible();
      const planning = page.getByRole("form", { name: "Параметры подбора" });
      await planning.getByLabel("Окончание, по Москве").fill(new Date(new Date(end).getTime() + 3 * 3600000).toISOString().slice(0, 16));
      await planning.getByRole("button", { name: "Сохранить параметры", exact: true }).click();
      await expect(panel.getByRole("heading", { name: "Уточнить окно события", exact: true })).toHaveCount(0);
      const offers: { id: string; booking_id: string }[] = [];
      for (const [kind, id, index] of [["artist", artist.id, 0], ["hall", venue.hall_id, 1]] as const) {
        const slot = await postJson<{ id: string }>(request, "/slots", supplier.token, { resource_type: kind, resource_id: id, starts_at: new Date(startMs - 3600000).toISOString(), ends_at: new Date(startMs + 4 * 3600000).toISOString() });
        const req = await postJson<{ id: string }>(request, `/events/${event.id}/requests`, customer.token, { resource_type: kind, resource_id: id, requirement_id: event.requirements[index].id });
        offers.push(await postJson(request, `/requests/${req.id}/offers`, supplier.token, { slot_id: slot.id, honorarium_rub: 100000 }));
      }
      await panel.getByRole("button", { name: "Обновить готовность" }).click();
      await expect(panel.getByRole("heading", { name: "Проверить условия предложения", exact: true })).toBeVisible();
      await expect(page.getByText("Все роли в составе закрыты", { exact: false })).toHaveCount(0);
      for (const offer of offers) {
        for (const [side, actor] of [["customer", customer], ["supplier", supplier]] as const) await postJson(request, `/offers/${offer.id}/ack`, actor.token, { side });
        await postJson(request, `/bookings/${offer.booking_id}/hold`, customer.token, {});
      }
      await panel.getByRole("button", { name: "Обновить готовность" }).click();
      await expect(panel.getByRole("heading", { name: "Перейти к договору", exact: true })).toBeVisible();
      for (const offer of offers) {
        const contract = await postJson<{ id: string }>(request, `/bookings/${offer.booking_id}/contract`, customer.token, {});
        for (const [side, actor] of [["customer", customer], ["supplier", supplier]] as const) {
          const inbox = await getJson<{ items: { entity_id: string; body: string }[] }>(request, "/notifications?limit=100", actor.token);
          const otp = inbox.items.find((n) => n.entity_id === contract.id)?.body.match(/\b\d{6}\b/)?.[0]; expect(otp).toBeTruthy();
          await postJson(request, `/contracts/${contract.id}/sign`, actor.token, { side, otp });
        }
        const payment = await postJson<{ id: string }>(request, `/bookings/${offer.booking_id}/payments`, customer.token, { idempotency_key: `ready-${offer.id}` });
        await postJson(request, `/payments/${payment.id}/stub-complete`, customer.token, {});
      }
      await panel.getByRole("button", { name: "Обновить готовность" }).click();
      await expect(panel.getByRole("progressbar")).toHaveAttribute("value", "100");
      await expect(panel).toContainText("2 из 2 обязательных позиций подтверждено сделками");
      await expect(panel).toContainText("Деньги не списывались");
      await panel.evaluate((element) => { const header = document.querySelector("header.top"); window.scrollBy({ top: element.getBoundingClientRect().top - (header?.getBoundingClientRect().height || 0) - 16, behavior: "instant" }); });
      await page.screenshot({ path: testInfo.outputPath("readiness-viewport.png") });
      await page.goto("/cabinet/customer");
      const overview = page.getByRole("region", { name: "Продолжить организацию событий", exact: true });
      await expect(overview.getByRole("link", { name: "Корпоратив с проверками", exact: true })).toBeVisible();
      await expect(overview.getByRole("progressbar")).toHaveAttribute("value", "100");
      await expect(overview.getByRole("link", { name: "Продолжить организацию", exact: true })).toHaveAttribute("href", `/events/${event.id}#event-day`);
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
      await overview.evaluate((element) => { const header = document.querySelector("header.top"); window.scrollBy({ top: element.getBoundingClientRect().top - (header?.getBoundingClientRect().height || 0) - 16, behavior: "instant" }); });
      await page.screenshot({ path: testInfo.outputPath("customer-readiness-viewport.png") });
      expect((await request.put(`${API_BASE}/halls/${venue.hall_id}/technical`, { headers: { Authorization: `Bearer ${supplier.token}` }, data: { ...hallFacts, expected_version: 1, equipment: [] } })).ok()).toBe(true);
      await page.goto(`/events/${event.id}`);
      await expect(panel.getByRole("heading", { name: "Согласовать технические условия", exact: true })).toBeVisible();
      await expect(panel.getByRole("progressbar")).not.toHaveAttribute("value", "100");
      await panel.getByRole("link", { name: "Продолжить организацию", exact: true }).click();
      await expect(page).toHaveURL(new RegExp(`/compatibility\\?event=${event.id}&artist=${artist.id}&venue=${venue.id}&hall=${venue.hall_id}`));
      await expect(page.getByRole("combobox", { name: "Зал", exact: true })).toHaveValue(venue.hall_id);
    });
  });
}
