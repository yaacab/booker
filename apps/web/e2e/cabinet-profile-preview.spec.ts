import { expect, test } from "@playwright/test";
import { API_BASE, DEMO_ACCOUNTS, fetchMe, injectSession, login } from "./helpers";

test.describe("private cabinet profile preview", () => {
  test.setTimeout(90_000);

  test("unpublished profile stays HTTP 404 publicly but renders from an authorized browser response", async ({ page, request }) => {
    const id = "private-draft-preview";
    const title = "Черновик для предпросмотра";
    const publicResponse = await request.get(`/artists/${id}`);
    expect(publicResponse.status()).toBe(404);
    const previewResponse = await request.get(`/cabinet/preview/artist/${id}`);
    expect(previewResponse.status()).toBe(200);
    expect(await previewResponse.text()).not.toContain(title);

    await injectSession(page, "preview-owner-token", "preview-owner-org");
    await page.route(`${API_BASE}/me`, async (route) => {
      expect(route.request().headers().authorization).toBe("Bearer preview-owner-token");
      await route.fulfill({ json: { organizations: [{ id: "preview-owner-org", kind: "artist" }] } });
    });
    await page.route(`${API_BASE}/organizations/preview-owner-org/calendar-targets`, async (route) => {
      expect(route.request().headers().authorization).toBe("Bearer preview-owner-token");
      await route.fulfill({ json: { items: [{ resource_type: "artist", resource_id: id }] } });
    });
    await page.route(`${API_BASE}/artists/${id}`, async (route) => {
      expect(route.request().headers().authorization).toBe("Bearer preview-owner-token");
      await route.fulfill({ json: { id, name: title, city: "Москва", tariffs: [], slots: [] } });
    });

    await page.goto(`/cabinet/preview/artist/${id}`);
    await expect(page.getByRole("heading", { name: title })).toBeVisible();
    await expect(page.locator("[aria-label='Профиль']")).toBeVisible();
  });

  test("same-tab organization and account changes clear a rendered preview and discard a delayed old response", async ({ page }) => {
    const id = "same-tab-private-preview";
    const privateName = "Закрытый профиль владельца";
    let profileRequests = 0;
    let releaseDelayed: (() => void) | undefined;
    let markDelayedStarted: (() => void) | undefined;
    const delayedStarted = new Promise<void>((resolve) => { markDelayedStarted = resolve; });

    await injectSession(page, "owner-token", "owner-org");
    await page.route(`${API_BASE}/me`, async (route) => {
      const token = route.request().headers().authorization;
      await route.fulfill({ json: {
        organizations: token === "Bearer owner-token"
          ? [{ id: "owner-org", kind: "artist" }, { id: "other-org", kind: "artist" }]
          : [{ id: "outsider-org", kind: "customer" }],
      } });
    });
    await page.route(`${API_BASE}/organizations/owner-org/calendar-targets`, async (route) => {
      await route.fulfill({ json: { items: [{ resource_type: "artist", resource_id: id }] } });
    });
    await page.route(`${API_BASE}/organizations/other-org/calendar-targets`, async (route) => {
      await route.fulfill({ json: { items: [] } });
    });
    await page.route(`${API_BASE}/artists/${id}`, async (route) => {
      profileRequests += 1;
      if (profileRequests === 2) {
        markDelayedStarted?.();
        await new Promise<void>((resolve) => { releaseDelayed = resolve; });
      }
      await route.fulfill({ json: { id, name: privateName, city: "Москва", tariffs: [], slots: [] } });
    });

    await page.goto(`/cabinet/preview/artist/${id}`);
    await expect(page.getByRole("heading", { name: privateName })).toBeVisible();

    // The session event below is what setActiveOrg emits; storage alone does not notify this tab.
    await page.evaluate(() => {
      localStorage.setItem("booker.org", "other-org");
      window.dispatchEvent(new Event("booker:session-changed"));
    });
    await expect(page.getByRole("heading", { name: privateName })).toHaveCount(0);
    await expect(page.locator("p[role='alert']")).toContainText("Профиль недоступен");

    await page.evaluate(() => {
      localStorage.setItem("booker.org", "owner-org");
      window.dispatchEvent(new Event("booker:session-changed"));
    });
    await delayedStarted;
    await page.evaluate(() => {
      localStorage.setItem("booker.token", "outsider-token");
      window.dispatchEvent(new Event("booker:session-changed"));
      localStorage.setItem("booker.org", "outsider-org");
      window.dispatchEvent(new Event("booker:session-changed"));
    });
    await expect(page.getByRole("heading", { name: privateName })).toHaveCount(0);
    await expect(page.locator("p[role='alert']")).toContainText("Профиль недоступен");

    const oldResponse = page.waitForResponse((response) => response.url() === `${API_BASE}/artists/${id}`);
    releaseDelayed?.();
    await oldResponse;
    await page.waitForTimeout(250);
    await expect(page.getByRole("heading", { name: privateName })).toHaveCount(0);
    await expect(page.locator("[aria-label='Профиль']")).toHaveCount(0);
    expect(profileRequests).toBe(2);
  });

  for (const kind of ["artist", "venue"] as const) {
    test(`${kind}: owner sees browser-fetched profile; guest and outsider see no data`, async ({ page, request, browser }) => {
      const account = kind === "artist" ? DEMO_ACCOUNTS.artist : DEMO_ACCOUNTS.venue;
      const owner = await login(request, account);
      const me = await fetchMe(request, owner.token);
      const org = me.organizations.find((item) => item.kind === kind);
      expect(org?.id).toBeTruthy();
      const targetsResponse = await request.get(`${API_BASE}/organizations/${org!.id}/calendar-targets`, {
        headers: { Authorization: `Bearer ${owner.token}` },
      });
      expect(targetsResponse.ok()).toBeTruthy();
      const targets = await targetsResponse.json() as {
        items: { resource_type: string; resource_id: string; venue_id?: string }[];
      };
      const id = kind === "artist"
        ? targets.items.find((item) => item.resource_type === "artist")?.resource_id
        : targets.items.find((item) => item.venue_id)?.venue_id;
      expect(id).toBeTruthy();
      const path = `/cabinet/preview/${kind}/${id}`;
      const apiProfileResponse = await request.get(`${API_BASE}/${kind === "artist" ? "artists" : "venues"}/${id}`, {
        headers: { Authorization: `Bearer ${owner.token}` },
      });
      expect(apiProfileResponse.ok()).toBeTruthy();
      const apiProfile = await apiProfileResponse.json() as { name: string };

      const serverResponse = await request.get(path);
      expect(serverResponse.status()).toBe(200);
      const serverHtml = await serverResponse.text();
      expect(serverHtml).toContain('name="robots" content="noindex, nofollow"');
      expect(serverHtml).not.toContain(apiProfile.name);

      const guest = await browser.newPage();
      try {
        await guest.goto(path);
        await expect(guest.locator("p[role='alert']")).toContainText("Профиль недоступен");
        await expect(guest.locator("[aria-label='Профиль']")).toHaveCount(0);
      } finally {
        await guest.close();
      }

      const outsider = await login(request, DEMO_ACCOUNTS.customer);
      const outsiderMe = await fetchMe(request, outsider.token);
      const outsiderOrg = outsiderMe.organizations.find((item) => item.kind === "customer");
      expect(outsiderOrg?.id).toBeTruthy();
      let outsiderProfileRequests = 0;
      await page.route(`${API_BASE}/${kind === "artist" ? "artists" : "venues"}/${id}`, async (route) => {
        outsiderProfileRequests += 1;
        await route.continue();
      });
      await injectSession(page, outsider.token, outsiderOrg!.id);
      await page.goto(path);
      await expect(page.locator("p[role='alert']")).toContainText("Профиль недоступен");
      await expect(page.locator("[aria-label='Профиль']")).toHaveCount(0);
      expect(outsiderProfileRequests).toBe(0);

      const ownerPage = await browser.newPage();
      try {
        await injectSession(ownerPage, owner.token, org!.id);
        await ownerPage.goto(path);
        await expect(ownerPage.locator("[aria-label='Профиль']")).toBeVisible();
        await expect(ownerPage.getByRole("heading", { name: apiProfile.name })).toBeVisible();
      } finally {
        await ownerPage.close();
      }
    });
  }
});
