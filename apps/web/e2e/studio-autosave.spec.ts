import { expect, test } from "@playwright/test";
import { API_BASE, DEMO_ACCOUNTS, apiHealth, fetchMe, injectSession, login } from "./helpers";

const CLASSIC_DRAFT_KEY = "booker.eventDraft";
const MAP_DRAFT_KEY = "booker.eventStudioMapDraft";
const SUBMIT_KEY = "booker.eventStudioSubmitKey";

async function clearStudioStorage(page: import("@playwright/test").Page) {
  await page.evaluate(
    ({ classic, map, submit }) => {
      localStorage.removeItem(classic);
      localStorage.removeItem(map);
      sessionStorage.removeItem(submit);
      sessionStorage.removeItem(`${submit}:result`);
    },
    { classic: CLASSIC_DRAFT_KEY, map: MAP_DRAFT_KEY, submit: SUBMIT_KEY },
  );
}

test.describe("E06 Event Studio autosave", () => {
  test("классический мастер: draft переживает reload (map flag OFF)", async ({ page }) => {
    await page.goto("/events/new");
    await clearStudioStorage(page);
    await page.reload();

    await expect(page.getByRole("heading", { name: "Новая заявка" })).toBeVisible();
    await expect(page.getByText("Event Studio · 8 шагов")).toBeVisible();
    await expect(page.locator(".event-studio-shell")).toHaveCount(0);

    const unique = `E06 Classic ${Date.now()}`;
    await page.getByPlaceholder("Например, выпускной или презентация").fill(unique);

    await expect
      .poll(async () => page.evaluate((key) => localStorage.getItem(key) || "", CLASSIC_DRAFT_KEY), {
        timeout: 5_000,
      })
      .toContain(unique);
    await expect(page.getByRole("status")).toContainText(/Сохран/i);

    await page.reload();
    await expect(page.getByRole("heading", { name: "Новая заявка" })).toBeVisible();
    await expect(page.getByPlaceholder("Например, выпускной или презентация")).toHaveValue(unique);
  });

  test("map UI: draft переживает reload (query flag on only)", async ({ page }) => {
    await page.goto("/events/new?event_studio_map_v1=1");
    await clearStudioStorage(page);
    await page.reload();

    await expect(page.locator(".event-studio-shell")).toBeVisible();
    const unique = `E06 Map ${Date.now()}`;
    await page.getByLabel("Название события").fill(unique);

    await expect
      .poll(async () => page.evaluate((key) => localStorage.getItem(key) || "", MAP_DRAFT_KEY), {
        timeout: 5_000,
      })
      .toContain(unique);

    await page.reload();
    await expect(page.locator(".event-studio-shell")).toBeVisible();
    await expect(page.getByLabel("Название события")).toHaveValue(unique);
  });

  test("offline: статус и локальный draft без сетевых хаков", async ({ page, context }) => {
    await page.goto("/events/new");
    await clearStudioStorage(page);
    await page.reload();
    await expect(page.getByRole("heading", { name: "Новая заявка" })).toBeVisible();

    await context.setOffline(true);
    const unique = `E06 Offline ${Date.now()}`;
    await page.getByPlaceholder("Например, выпускной или презентация").fill(unique);

    await expect(page.getByRole("status")).toContainText(/Без сети/i);
    await expect
      .poll(async () => page.evaluate((key) => localStorage.getItem(key) || "", CLASSIC_DRAFT_KEY), {
        timeout: 5_000,
      })
      .toContain(unique);

    await context.setOffline(false);
    await page.getByPlaceholder("Например, выпускной или презентация").fill(`${unique} · online`);
    await expect(page.getByRole("status")).toContainText(/Сохран/i, { timeout: 5_000 });
  });

  test("map: retry с тем же submit key не создаёт второй POST /events", async ({ page, request }) => {
    test.skip(!(await apiHealth(request)), `API недоступен (${API_BASE})`);

    const session = await login(request, DEMO_ACCOUNTS.customer);
    const me = await fetchMe(request, session.token);
    const org = me.organizations.find((o) => o.kind === "customer");
    test.skip(!org, "нет customer org — нужен make seed");

    const cachedEventId = `e06-cached-${Date.now()}`;
    await page.addInitScript(
      ({ draftKey, submitKey, eventId }) => {
        localStorage.setItem(
          draftKey,
          JSON.stringify({
            draft: {
              title: "E06 Idem Retry",
              kind: "Свадьба",
              city: "Москва",
              date: "",
              startsAt: "17:00",
              endsAt: "23:30",
              guests: 80,
              talentIds: [],
              requirements: [],
              version: 2,
            },
            savedAt: new Date().toISOString(),
          }),
        );
        // Prior successful create in this tab — retry must reuse, not POST again.
        sessionStorage.setItem(submitKey, "e06-stable-submit-key");
        sessionStorage.setItem(`${submitKey}:result`, eventId);
      },
      { draftKey: MAP_DRAFT_KEY, submitKey: SUBMIT_KEY, eventId: cachedEventId },
    );
    await injectSession(page, session.token, org!.id);

    let eventPosts = 0;
    await page.route("**/events", async (route) => {
      if (route.request().method() !== "POST") {
        await route.continue();
        return;
      }
      const path = new URL(route.request().url()).pathname.replace(/\/$/, "");
      // Exact create only — not /analytics/events or /events/:id/requests.
      if (path !== "/events") {
        await route.continue();
        return;
      }
      eventPosts += 1;
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ id: `should-not-create-${eventPosts}`, requirements: [] }),
      });
    });

    await page.goto("/events/new?event_studio_map_v1=1");
    await expect(page.locator(".event-studio-shell")).toBeVisible();
    await expect(page.getByLabel("Название события")).toHaveValue("E06 Idem Retry");

    await page.getByRole("button", { name: "Проверка" }).click();
    await page.getByRole("button", { name: /Продолжить/ }).click();

    await expect(page).toHaveURL(new RegExp(`/events/${cachedEventId}`), { timeout: 10_000 });
    expect(eventPosts).toBe(0);
  });
});
