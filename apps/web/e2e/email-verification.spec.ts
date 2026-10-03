import { expect, test } from "@playwright/test";

test("registration requiring email proof waits before creating an organization", async ({ page }) => {
  let orgCreates = 0;
  await page.route("**/auth/register", async (route) => {
    await route.fulfill({
      status: 200,
      contentType: "application/json",
      body: JSON.stringify({ token: "pending-email-token", email_verification_required: true }),
    });
  });
  await page.route("**/orgs", async (route) => {
    if (route.request().method() === "POST") orgCreates += 1;
    await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ id: "new-org" }) });
  });

  await page.goto("/login");
  await page.getByRole("button", { name: "Создать аккаунт" }).click();
  await page.getByTestId("role-option-artist").click();
  await page.locator('input[name="full_name"]').fill("Новый исполнитель");
  await page.locator('input[name="email"]').fill("new-performer@booker.test");
  await page.locator('input[name="password"]').fill("password1");
  await page.locator("#accept_offer").check();
  await page.locator("#accept_privacy").check();
  await page.locator("#accept_consent_texts").check();
  await page.locator("#draft_test_acknowledgement").check();
  await page.getByRole("button", { name: "Создать аккаунт" }).click();
  await expect(page.getByRole("heading", { name: "Подтвердить email" })).toBeVisible();
  expect(orgCreates).toBe(0);

  await page.route("**/auth/login", async (route) => {
    await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ token: "verified-email-token" }) });
  });
  await page.route("**/auth/email-verification/confirm", async (route) => {
    expect(route.request().postDataJSON()).toEqual({ token: "proof-token" });
    await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ email_verified: true }) });
  });
  await page.route("**/me", async (route) => {
    await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify({ organizations: [] }) });
  });
  await page.goto("/login#verify=proof-token");
  await expect(page).toHaveURL(/\/login$/);
  await page.locator('input[name="email"]').fill("new-performer@booker.test");
  await page.locator('input[name="password"]').fill("password1");
  await page.getByRole("button", { name: "Подтвердить адрес" }).click();
  await expect(page.getByRole("heading", { name: "Создать рабочее пространство" })).toBeVisible();
  expect(orgCreates).toBe(0);
});
