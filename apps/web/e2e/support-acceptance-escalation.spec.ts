import { expect, test } from "@playwright/test";
import { execFileSync } from "node:child_process";
import { API_BASE, DEMO_ACCOUNTS, injectSession, login } from "./helpers";
import { demoTotp } from "./totp-fixture";

test("unaccepted urgent ticket reaches admin with its own acceptance deadline", async ({ page, request }) => {
  const database = process.env.BOOKER_DATABASE_URL ?? "";
  test.skip(process.env.BOOKER_RUNTIME_ENV !== "test" || !database.startsWith("sqlite:////tmp/"), "isolated fixture required");
  const customer = await login(request, DEMO_ACCOUNTS.customer);
  const result = await request.post(`${API_BASE}/support/tickets`, {
    headers: { Authorization: `Bearer ${customer.token}`, "Idempotency-Key": `acceptance-${Date.now()}` },
    data: { category: "technical", subject: "Исполнитель не приехал", body: "Исполнитель на мероприятие сегодня не приехал" },
  });
  expect(result.status()).toBe(201);
  const ticket = await result.json() as { id: string };
  execFileSync("../api/.venv/bin/python", ["-c", `
import sys
from pathlib import Path
sys.path.insert(0, str(Path('../api').resolve()))
from datetime import datetime, timezone
from booker_api.db import SessionLocal
from booker_api.models import SupportTicket
from booker_api.support_escalation import escalate_unaccepted
with SessionLocal() as db:
    row = db.get(SupportTicket, sys.argv[1])
    row.created_at = datetime(2026,10,3,7,0,tzinfo=timezone.utc)
    row.priority = 'urgent'
    db.commit()
    result = escalate_unaccepted(db, at=datetime(2026,10,3,7,15,tzinfo=timezone.utc))
    assert result['escalated'] == 1, result
`, ticket.id], { cwd: process.cwd() });
  const admin = await login(request, DEMO_ACCOUNTS.admin);
  await injectSession(page, admin.token, "");
  await page.setViewportSize({ width: 390, height: 844 });
  await page.goto("/admin");
  const queue = page.getByRole("region", { name: "Очередь поддержки" });
  await queue.getByLabel("Код 2FA").fill(demoTotp());
  await queue.getByRole("button", { name: "Показать очередь" }).click();
  await queue.getByRole("button", { name: new RegExp(`SUP-${ticket.id.slice(0,8).toUpperCase()}`) }).click();
  await expect(queue.getByText(/Принять до:.*15 рабочих минут/)).toBeVisible();
  await expect(queue.getByText("Срок принятия истёк — обращение передано администратору.")).toBeVisible();
  await queue.getByLabel("Код 2FA").fill(demoTotp());
  await queue.getByRole("button", { name: "Подтвердить принятие" }).click();
  await expect(queue.getByText(/Принятие: подтверждено/)).toBeVisible();
  const customerView = await request.get(`${API_BASE}/support/tickets/${ticket.id}`, {
    headers: { Authorization: `Bearer ${customer.token}` },
  });
  expect(await customerView.json()).not.toHaveProperty("acceptance_escalated_at");
});
