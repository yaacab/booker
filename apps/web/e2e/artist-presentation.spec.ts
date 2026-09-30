import { expect, test } from "@playwright/test";
import { API_BASE, injectSession, postJson, register } from "./helpers";

for (const width of [1440, 390]) {
  test.describe(`Artist presentation ${width}px`, () => {
    test.use({ viewport: { width, height: 900 } });
    test("Free artist edits a complete public showcase with honest trust facts", async ({ page, request }, testInfo) => {
      const actor = await register(request, `epk-${width}-${Date.now()}@booker.test`, "Артист");
      const org = await postJson<{ id: string }>(request, "/orgs", actor.token, { name: "Концертная программа", kind: "artist" });
      const artist = await postJson<{ id: string }>(request, "/artists", actor.token, { organization_id: org.id, name: "Сцена", city: "Москва", category: "cover" });
      await postJson(request, `/artists/${artist.id}/tariffs`, actor.token, { title: "Два отделения", honorarium_rub: 88000, hours: 2 });
      await page.route("https://media.example.org/**", (route) => route.fulfill({ contentType: "image/svg+xml", body: '<svg xmlns="http://www.w3.org/2000/svg" width="1200" height="600"><rect width="1200" height="600" fill="#315542"/><circle cx="900" cy="180" r="100" fill="#c6fb42"/><text x="65" y="370" fill="#fff" font-size="45">Материал артиста · тест</text></svg>' }));
      await injectSession(page, actor.token, org.id);
      await page.goto("/cabinet/performer/presentation");
      const form = page.getByRole("form", { name: "Редактор витрины" });
      await form.getByLabel("Имя на афише", { exact: true }).fill("Акустическая сцена");
      await form.getByLabel("Формат", { exact: true }).fill("Камерный концерт");
      await form.getByLabel("Состав", { exact: true }).fill("Вокал, гитара, перкуссия");
      await form.getByLabel("Программа", { exact: true }).fill("Два отделения: джаз и акустические версии знакомых песен.");
      await form.getByLabel("Длительность, минут", { exact: true }).fill("90");
      await form.getByLabel("Города выезда", { exact: false }).fill("Тула\nКалуга");
      await form.getByLabel("Обложка — ссылка на изображение", { exact: true }).fill("https://media.example.org/cover.svg");
      await form.getByLabel("Основное видео выступления", { exact: true }).fill("https://video.example.org/performance");
      await form.getByLabel("Галерея — ссылки по одной на строке", { exact: true }).fill("https://media.example.org/gallery.svg");
      await form.getByLabel("Подтверждаю право публиковать эти материалы", { exact: true }).check();
      await form.getByLabel("Площадь сцены, м²", { exact: true }).fill("12");
      await form.getByLabel("Микрофоны, шт.", { exact: true }).fill("2");
      await form.getByLabel("Условия и технические требования", { exact: true }).fill("Нужен сухой доступ к сцене.");
      await form.getByRole("button", { name: "Сохранить публичную витрину" }).click();
      await expect(page.getByRole("status").filter({ hasText: "Публичная витрина сохранена" })).toBeVisible();
      await page.reload();
      await expect(page.getByRole("textbox", { name: "Программа", exact: true })).toHaveValue("Два отделения: джаз и акустические версии знакомых песен.");
      await page.goto(`/artists/${artist.id}`);
      await expect(page.getByRole("heading", { name: "Акустическая сцена", exact: true })).toBeVisible();
      await expect(page.getByText("Продолжительность: 90 мин.")).toBeVisible();
      await expect(page.getByText("Нужен сухой доступ к сцене.")).toBeVisible();
      await expect(page.getByRole("link", { name: "Посмотреть выступление ↗" })).toHaveAttribute("href", "https://video.example.org/performance");
      const completedDeals = page.locator(".profile-facts-strip > div").filter({ hasText: "Завершённых сделок" });
      await expect(completedDeals.locator("dt")).toHaveText("Завершённых сделок");
      await expect(completedDeals.locator("dd")).toHaveText("0");
      await expect(page.getByText("Завершённых сделок с отзывами пока нет.")).toBeVisible();
      await expect(page.getByText("88 000 ₽", { exact: true })).toBeVisible();
      await expect(page.getByText("Окончательная стоимость и условия — в предложении после заявки.", { exact: true })).toBeVisible();
      await page.getByRole("button", { name: "Сравнить", exact: true }).click();
      await expect(page.getByRole("button", { name: "Убрать из сравнения" })).toBeVisible();
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= window.innerWidth)).toBe(true);
      await page.screenshot({ path: testInfo.outputPath("artist-showcase.png"), fullPage: true });
      const publicProfile = await request.get(`${API_BASE}/artists/${artist.id}`);
      expect((await publicProfile.json()).verified).toBe(false);
    });
  });
}

test("public profile recovers after a failed request", async ({ page, request }) => {
  const actor = await register(request, `epk-error-${Date.now()}@booker.test`, "Артист");
  const org = await postJson<{ id: string }>(request, "/orgs", actor.token, { name: "Витрина", kind: "artist" });
  const artist = await postJson<{ id: string }>(request, "/artists", actor.token, { organization_id: org.id, name: "Восстановленная витрина", category: "dj" });
  let profileRequests = 0;
  await page.route(`${API_BASE}/artists/${artist.id}`, async (route) => {
    profileRequests += 1;
    if (profileRequests === 1) {
      await route.fulfill({
        status: 503,
        contentType: "application/json",
        body: JSON.stringify({ detail: "private upstream failure" }),
      });
      return;
    }
    await route.continue();
  });
  await page.goto(`/artists/${artist.id}`);
  await expect(page.getByRole("alert").filter({ hasText: "Не удалось загрузить профиль" })).toBeVisible();
  await expect(page.getByText("private upstream failure")).toHaveCount(0);
  await page.getByRole("button", { name: "Повторить загрузку" }).click();
  await expect(page.getByRole("heading", { name: "Восстановленная витрина", exact: true })).toBeVisible();
  expect(profileRequests).toBe(2);
});
