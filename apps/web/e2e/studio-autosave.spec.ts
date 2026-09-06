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

  test("map: повторный submit под lock не дублирует POST /events", async ({ page, request }) => {
    test.skip(!(await apiHealth(request)), `API недоступен (${API_BASE})`);

    const session = await login(request, DEMO_ACCOUNTS.customer);
    const me = await fetchMe(request, session.token);
    const org = me.organizations.find((o) => o.kind === "customer");
    test.skip(!org, "нет customer org — нужен make seed");

    await page.addInitScript(() => {
      sessionStorage.removeItem("booker.eventStudioSubmitKey");
      sessionStorage.removeItem("booker.eventStudioSubmitKey:result");
      localStorage.removeItem("booker.eventStudioMapDraft");
    });
    await injectSession(page, session.token, org!.id);

    let releasePost!: () => void;
    const postGate = new Promise<void>((resolve) => {
      releasePost = resolve;
    });
    let eventPosts = 0;

    await page.route("**/events", async (route) => {
      if (route.request().method() !== "POST") {
        await route.continue();
        return;
      }
      // Only the create endpoint — not /events/:id/requests.
      const url = route.request().url().replace(/\/$/, "");
      if (!/\/events$/.test(url)) {
        await route.continue();
        return;
      }
      eventPosts += 1;
      await postGate;
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ id: `e06-idem-${eventPosts}`, requirements: [] }),
      });
    });
    await page.route("**/events/*/requests", async (route) => {
      if (route.request().method() === "POST") {
        await route.fulfill({ status: 200, contentType: "application/json", body: "{}" });
        return;
      }
      await route.continue();
    });

    await page.goto("/events/new?event_studio_map_v1=1");
    await expect(page.locator(".event-studio-shell")).toBeVisible();

    await page.getByLabel("Название события").fill(`E06 Idem ${Date.now()}`);
    await page.getByRole("button", { name: "Проверка" }).click();
    const continueBtn = page.getByRole("button", { name: /Продолжить/ });
    await expect(continueBtn).toBeVisible();

    const firstClick = continueBtn.click();
    await expect.poll(() => eventPosts, { timeout: 10_000 }).toBe(1);

    // Second click while first POST is held — submitLock must drop it.
    await continueBtn.click({ force: true }).catch(() => undefined);
    await page.waitForTimeout(400);
    expect(eventPosts).toBe(1);

    releasePost();
    await firstClick;
    await expect
      .poll(async () => page.evaluate((k) => sessionStorage.getItem(`${k}:result`) || "", SUBMIT_KEY), {
        timeout: 10_000,
      })
      .toMatch(/^e06-idem-/);
    expect(eventPosts).toBe(1);
  });

  test("map: abort POST затем retry — один event, тот же submit key", async ({ page, request }) => {
    test.skip(!(await apiHealth(request)), `API недоступен (${API_BASE})`);

    const session = await login(request, DEMO_ACCOUNTS.customer);
    const me = await fetchMe(request, session.token);
    const org = me.organizations.find((o) => o.kind === "customer");
    test.skip(!org, "нет customer org — нужен make seed");

    await page.addInitScript(() => {
      sessionStorage.removeItem("booker.eventStudioSubmitKey");
      sessionStorage.removeItem("booker.eventStudioSubmitKey:result");
      localStorage.removeItem("booker.eventStudioMapDraft");
    });
    await injectSession(page, session.token, org!.id);

    let eventPosts = 0;
    let successfulCreates = 0;
    let abortNextCreate = true;

    await page.route("**/events", async (route) => {
      if (route.request().method() !== "POST") {
        await route.continue();
        return;
      }
      const url = route.request().url().replace(/\/$/, "");
      if (!/\/events$/.test(url)) {
        await route.continue();
        return;
      }
      eventPosts += 1;
      if (abortNextCreate) {
        abortNextCreate = false;
        await route.abort("failed");
        return;
      }
      successfulCreates += 1;
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({ id: "e06-retry-ok", requirements: [] }),
      });
    });
    await page.route("**/events/*/requests", async (route) => {
      if (route.request().method() === "POST") {
        await route.fulfill({ status: 200, contentType: "application/json", body: "{}" });
        return;
      }
      await route.continue();
    });

    await page.goto("/events/new?event_studio_map_v1=1");
    await expect(page.locator(".event-studio-shell")).toBeVisible();

    await page.getByLabel("Название события").fill(`E06 Retry ${Date.now()}`);
    await page.getByRole("button", { name: "Проверка" }).click();
    const continueBtn = page.getByRole("button", { name: /Продолжить/ });
    await expect(continueBtn).toBeVisible();

    const submitKeyBefore = await page.evaluate((k) => sessionStorage.getItem(k) || "", SUBMIT_KEY);
    expect(submitKeyBefore.length).toBeGreaterThan(0);

    await continueBtn.click();
    await expect(page.getByRole("alert")).toBeVisible({ timeout: 10_000 });
    await expect.poll(() => eventPosts, { timeout: 5_000 }).toBe(1);
    expect(successfulCreates).toBe(0);
    await expect
      .poll(async () => page.evaluate((k) => sessionStorage.getItem(`${k}:result`), SUBMIT_KEY), {
        timeout: 2_000,
      })
      .toBeNull();

    const submitKeyAfterFail = await page.evaluate((k) => sessionStorage.getItem(k) || "", SUBMIT_KEY);
    expect(submitKeyAfterFail).toBe(submitKeyBefore);

    await expect(continueBtn).toBeEnabled({ timeout: 5_000 });
    await continueBtn.click();

    await expect
      .poll(async () => page.evaluate((k) => sessionStorage.getItem(`${k}:result`) || "", SUBMIT_KEY), {
        timeout: 10_000,
      })
      .toBe("e06-retry-ok");
    expect(eventPosts).toBe(2);
    expect(successfulCreates).toBe(1);

    const submitKeyAfterOk = await page.evaluate((k) => sessionStorage.getItem(k) || "", SUBMIT_KEY);
    expect(submitKeyAfterOk).toBe(submitKeyBefore);
  });
});
