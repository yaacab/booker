import { expect, test, type APIRequestContext, type Page } from "@playwright/test";
import { API_BASE, apiHealth, DEMO_ACCOUNTS, fetchMe, injectSession, login } from "./helpers";

const MOBILE_VIEWPORT = { width: 390, height: 844 };

type CabinetRole = {
  label: string;
  account: string;
  orgKind: "customer" | "artist" | "venue";
  path: string;
  heading: string;
  dataCabinet: "customer" | "performer" | "venue";
};

const CABINET_ROLES: CabinetRole[] = [
  {
    label: "customer",
    account: DEMO_ACCOUNTS.customer,
    orgKind: "customer",
    path: "/cabinet/customer",
    heading: "Привет, Анна!",
    dataCabinet: "customer",
  },
  {
    label: "performer",
    account: DEMO_ACCOUNTS.artist,
    orgKind: "artist",
    path: "/cabinet/performer",
    heading: "Кабинет артиста",
    dataCabinet: "performer",
  },
  {
    label: "venue",
    account: DEMO_ACCOUNTS.venue,
    orgKind: "venue",
    path: "/cabinet/venue",
    heading: "Кабинет площадки",
    dataCabinet: "venue",
  },
];

async function openCabinet(
  page: Page,
  request: APIRequestContext,
  role: CabinetRole,
): Promise<void> {
  const session = await login(request, role.account);
  const me = await fetchMe(request, session.token);
  const org = me.organizations.find((o) => o.kind === role.orgKind);
  if (!org) throw new Error(`Demo ${role.orgKind} org missing — run make seed`);

  await page.emulateMedia({ reducedMotion: "reduce" });
  await injectSession(page, session.token, org.id);
  await page.goto(role.path);
}

async function expectCabinetCoreA11y(page: Page, role: CabinetRole): Promise<void> {
  await expect(page.getByRole("heading", { level: 1, name: role.heading })).toBeVisible({
    timeout: 15_000,
  });

  const main = page.locator(`main[data-cabinet="${role.dataCabinet}"]`);
  await expect(main).toBeVisible();
  await expect(main).toHaveAttribute("aria-labelledby", "cabinet-heading");
  await expect(page.locator("#cabinet-heading")).toBeVisible();

  await page.keyboard.press("Tab");
  const focused = page.locator(":focus");
  await expect(focused).toHaveAttribute("href", "#content");
  await expect(focused).toHaveAccessibleName(/содержан/i);

  const skipToWidgets = page.getByRole("link", { name: "К виджетам кабинета" });
  await expect(skipToWidgets).toHaveCount(1);
  await skipToWidgets.focus();
  await expect(skipToWidgets).toBeFocused();
  await page.keyboard.press("Enter");
  await expect(page.getByRole("region", { name: "Виджеты кабинета" })).toBeInViewport();

  await expect(page.getByRole("button", { name: "Выйти из аккаунта" })).toBeVisible();
}

test.describe("Cabinet a11y §7.5", () => {
  test.setTimeout(60_000);

  test("landmarks, skip links и клавиатурный фокус", async ({ page, request }) => {
    test.skip(!(await apiHealth(request)), `API недоступен (${API_BASE})`);

    const session = await login(request, DEMO_ACCOUNTS.customer);
    const me = await fetchMe(request, session.token);
    const org = me.organizations.find((o) => o.kind === "customer");
    if (!org) throw new Error("Demo customer org missing — run make seed");

    await page.emulateMedia({ reducedMotion: "reduce" });
    await injectSession(page, session.token, org.id);
    await page.goto("/cabinet/customer");

    await expect(page.getByRole("heading", { level: 1, name: "Привет, Анна!" })).toBeVisible({
      timeout: 15_000,
    });

    const main = page.locator('main[data-cabinet="customer"]');
    await expect(main).toHaveAttribute("aria-labelledby", "cabinet-heading");

    await page.keyboard.press("Tab");
    await expect(page.locator(":focus")).toHaveAttribute("href", "#content");

    const skipToWidgets = page.getByRole("link", { name: "К виджетам кабинета" });
    await expect(skipToWidgets).toHaveCount(1);
    await skipToWidgets.focus();
    await expect(skipToWidgets).toBeFocused();
    await page.keyboard.press("Enter");
    await expect(page.getByRole("region", { name: "Виджеты кабинета" })).toBeInViewport();

    const widgetsRegion = page.getByRole("region", { name: "Виджеты кабинета" });
    await expect(widgetsRegion).toBeVisible();

    await expect(page.getByRole("button", { name: "Выйти из аккаунта" })).toBeVisible();
  });

  test("performer cabinet: widget sections с aria-labelledby", async ({ page, request }) => {
    test.skip(!(await apiHealth(request)), `API недоступен (${API_BASE})`);

    const session = await login(request, DEMO_ACCOUNTS.artist);
    const me = await fetchMe(request, session.token);
    const org = me.organizations.find((o) => o.kind === "artist");
    if (!org) throw new Error("Demo artist org missing — run make seed");

    await page.emulateMedia({ reducedMotion: "reduce" });
    await injectSession(page, session.token, org.id);
    await page.goto("/cabinet/performer");

    await expect(page.getByRole("heading", { level: 1, name: "Кабинет артиста" })).toBeVisible({
      timeout: 15_000,
    });
    await expect(page.getByRole("heading", { level: 2, name: "Открытые слоты" })).toBeVisible();

    const widget = page.locator("section.dashboard-widget").first();
    await expect(widget).toBeVisible();
    const labelledBy = await widget.getAttribute("aria-labelledby");
    expect(labelledBy).toBeTruthy();
    if (labelledBy) {
      await expect(page.locator(`#${labelledBy}`)).toBeVisible();
    }
  });

  test("venue cabinet: landmarks, skip и клавиатурный фокус", async ({ page, request }) => {
    test.skip(!(await apiHealth(request)), `API недоступен (${API_BASE})`);

    await openCabinet(page, request, CABINET_ROLES[2]);
    await expectCabinetCoreA11y(page, CABINET_ROLES[2]);

    const widget = page.locator("section.dashboard-widget").first();
    await expect(widget).toBeVisible();
    const labelledBy = await widget.getAttribute("aria-labelledby");
    expect(labelledBy).toBeTruthy();
    if (labelledBy) {
      await expect(page.locator(`#${labelledBy}`)).toBeVisible();
    }
  });

  for (const role of CABINET_ROLES) {
    test(`mobile 390×844 ${role.label}: heading, main, Tab/skip`, async ({ page, request }) => {
      test.skip(!(await apiHealth(request)), `API недоступен (${API_BASE})`);

      await page.setViewportSize(MOBILE_VIEWPORT);
      await openCabinet(page, request, role);
      await expectCabinetCoreA11y(page, role);
    });
  }
});
