import { expect, test } from "@playwright/test";
import { API_BASE, apiHealth, injectSession } from "./helpers";

test("registration closes when displayed legal text hash differs from API", async ({ page, request }) => {
  test.skip(!(await apiHealth(request)), `API недоступен (${API_BASE})`);
  await page.goto("/login");
  await expect(page.getByRole("button", { name: "Создать аккаунт" })).toBeEnabled();
  const visible = await page.evaluate(async () => {
    const response = await fetch("/api/legal/visible-hashes", { cache: "no-store" });
    return response.json() as Promise<{ hashes: Record<string, string> }>;
  });
  let signalMismatch!: () => void;
  const mismatchRequested = new Promise<void>((resolve) => { signalMismatch = resolve; });
  await page.route("**/api/legal/visible-hashes", async (route) => {
    await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({
      hashes: { ...visible.hashes, cookies: "0".repeat(64) },
    }) });
    signalMismatch();
  });
  await page.reload();
  await mismatchRequested;
  await page.waitForLoadState("networkidle");
  await expect(page.getByRole("button", { name: "Создать аккаунт" })).toBeDisabled();
  await expect(page.locator("#accept_offer")).toHaveCount(0);
});

test("profile shows draft consent evidence and withdraws optional marketing", async ({ page, request }) => {
  test.skip(!(await apiHealth(request)), `API недоступен (${API_BASE})`);
  const packResponse = await request.get(`${API_BASE}/legal/pack`);
  expect(packResponse.status()).toBe(200);
  const pack = await packResponse.json() as {
    status: string;
    documents: Array<{ key: string; version: string; content_hash: string; required: boolean }>;
  };
  expect(pack.status).toBe("draft");
  const registered = await request.post(`${API_BASE}/auth/register`, {
    data: {
      email: `e2e-legal-${Date.now()}@booker.test`, password: "password1", full_name: "E2E Legal",
      accept_offer: true, accept_privacy: true, accept_processing: true,
      draft_test_acknowledgement: true, marketing_opt_in: true,
      accepted_documents: pack.documents.filter((document) => document.required).map(
        ({ key, version, content_hash }) => ({ key, version, content_hash }),
      ),
    },
  });
  expect(registered.status()).toBe(200);
  const user = await registered.json() as { token: string };
  await injectSession(page, user.token, "");
  await page.goto("/profile");
  const section = page.getByRole("region", { name: "Согласия и документы" });
  await expect(section).toBeVisible();
  await expect(section.getByText("Текущий пакет документов — черновик", { exact: false })).toBeVisible();
  await expect(section.getByText("Рассылка: есть тестовая отметка; действующего согласия нет.")).toBeVisible();
  await expect(section.getByRole("button", { name: "Принять текущую редакцию" })).toHaveCount(0);
  await section.getByRole("button", { name: "Отозвать тестовую отметку о рассылке" }).click();
  await expect(section.getByText("Рассылка: согласие не действует.")).toBeVisible();
  const history = await request.get(`${API_BASE}/me/consents`, {
    headers: { Authorization: `Bearer ${user.token}` },
  });
  expect(history.status()).toBe(200);
  const body = await history.json() as {
    marketing_email_active: boolean;
    marketing_test_selected: boolean;
    history: Array<{ kind: string; action: string; acceptance_effect: string | null }>;
  };
  expect(body.marketing_email_active).toBe(false);
  expect(body.marketing_test_selected).toBe(false);
  expect(body.history.filter((event) => event.kind === "marketing_email").map((event) => event.action))
    .toEqual(["accepted", "withdrawn"]);
  expect(body.history.filter((event) => event.action === "accepted").every(
    (event) => event.acceptance_effect === "test_acknowledgement",
  )).toBe(true);
});

test("late consent response cannot reveal previous account after token switch", async ({ page, request }) => {
  test.skip(!(await apiHealth(request)), `API недоступен (${API_BASE})`);
  const pack = await (await request.get(`${API_BASE}/legal/pack`)).json() as {
    documents: Array<{ key: string; version: string; content_hash: string; required: boolean }>;
  };
  async function create(marketing: boolean, label: string): Promise<string> {
    const response = await request.post(`${API_BASE}/auth/register`, { data: {
      email: `e2e-legal-switch-${label}-${Date.now()}@booker.test`,
      password: "password1", full_name: label,
      accept_offer: true, accept_privacy: true, accept_processing: true,
      draft_test_acknowledgement: true, marketing_opt_in: marketing,
      accepted_documents: pack.documents.filter((document) => document.required).map(
        ({ key, version, content_hash }) => ({ key, version, content_hash }),
      ),
    } });
    expect(response.status()).toBe(200);
    return (await response.json() as { token: string }).token;
  }
  const firstToken = await create(true, "old");
  const nextToken = await create(false, "new");
  let signalOldRequest!: () => void;
  const oldRequested = new Promise<void>((resolve) => { signalOldRequest = resolve; });
  let releaseOldResponse!: () => void;
  const oldResponseGate = new Promise<void>((resolve) => { releaseOldResponse = resolve; });
  await page.route("**/me/consents", async (route) => {
    const response = await route.fetch();
    if (route.request().headers().authorization === `Bearer ${firstToken}`) {
      signalOldRequest();
      await oldResponseGate;
    }
    await route.fulfill({ response });
  });
  await injectSession(page, firstToken, "");
  await page.goto("/profile");
  await oldRequested;
  const peer = await page.context().newPage();
  await peer.goto("/");
  await peer.evaluate((token) => localStorage.setItem("booker.token", token), nextToken);
  const section = page.getByRole("region", { name: "Согласия и документы" });
  await expect(section.getByText("Рассылка: согласие не действует.")).toBeVisible();
  releaseOldResponse();
  await expect(section.getByText("Рассылка: есть тестовая отметка; действующего согласия нет.")).toHaveCount(0);
  await expect(section.getByText("Рассылка: согласие не действует.")).toBeVisible();
  await peer.close();
});
