"use client";

import { FormEvent, useState } from "react";
import { api, ApiError } from "@/lib/api";

type Staff = { id: string; name: string; role: "operator" | "administrator" };
type Target = {
  id: string;
  recipient_user_id: string;
  channel: "cabinet" | "email" | "telegram";
  escalation_level: "primary" | "backup" | "administrator";
  active: boolean;
  schedule: { timezone: string; start: string; end: string };
  state_version: number;
};
type TargetsResponse = {
  items: Target[];
  email_transport_ready: boolean;
  telegram_transport_ready: boolean;
};

function headers(code: string, version?: number): Headers {
  const result = new Headers();
  if (code.trim()) result.set("X-Booker-TOTP", code.trim());
  if (version !== undefined) result.set("If-Match", String(version));
  return result;
}

function describeError(error: unknown): string {
  if (error instanceof ApiError) {
    if (error.status === 403) return "Нужны права администратора и действующая проверка 2FA.";
    if (error.status === 409) return "Настройка изменилась или адресат недоступен. Обновите список.";
  }
  return "Не удалось сохранить настройки. Проверьте соединение и повторите действие.";
}

export default function SupportNotificationTargets() {
  const [staff, setStaff] = useState<Staff[]>([]);
  const [targets, setTargets] = useState<TargetsResponse | null>(null);
  const [code, setCode] = useState("");
  const [staffId, setStaffId] = useState("");
  const [channel, setChannel] = useState<"cabinet" | "email">("cabinet");
  const [level, setLevel] = useState<"primary" | "backup" | "administrator">("administrator");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  async function refresh(event?: FormEvent) {
    event?.preventDefault();
    if (busy) return;
    setBusy(true);
    setError("");
    const currentCode = code.trim();
    setCode("");
    try {
      const [people, configured] = await Promise.all([
        api<{ items: Staff[] }>("/admin/support/staff", {
          headers: headers(currentCode), cache: "no-store",
        }),
        api<TargetsResponse>("/admin/support/notification-targets", {
          headers: headers(currentCode), cache: "no-store",
        }),
      ]);
      setStaff(people.items);
      setTargets(configured);
    } catch (failure) {
      setError(describeError(failure));
      setTargets(null);
    } finally {
      setBusy(false);
    }
  }

  async function configure(recipientId: string, selectedChannel: "cabinet" | "email" | "telegram",
    selectedLevel: "primary" | "backup" | "administrator", active: boolean) {
    if (busy) return;
    const existing = targets?.items.find((item) => item.recipient_user_id === recipientId
      && item.channel === selectedChannel && item.escalation_level === selectedLevel);
    const currentCode = code.trim();
    setCode("");
    setBusy(true);
    setError("");
    setNotice("");
    try {
      await api("/admin/support/notification-targets", {
        method: "POST",
        headers: headers(currentCode, existing?.state_version ?? 0),
        body: JSON.stringify({ recipient_user_id: recipientId, channel: selectedChannel,
          escalation_level: selectedLevel, active }),
      });
      const configured = await api<TargetsResponse>("/admin/support/notification-targets", {
        headers: headers(currentCode), cache: "no-store",
      });
      setTargets(configured);
      setNotice(active ? "Адресат включён. Реальная доставка зависит от настроенного транспорта."
        : "Адресат выключен. Неотправленные письма будут отменены перед отправкой.");
    } catch (failure) {
      setError(describeError(failure));
    } finally {
      setBusy(false);
    }
  }

  const selected = staff.find((person) => person.id === staffId);
  const allowedLevels = selected?.role === "administrator"
    ? ["administrator"] as const : ["primary", "backup"] as const;
  const effectiveLevel: "primary" | "backup" | "administrator" = selected?.role === "administrator"
    ? "administrator" : level === "backup" ? "backup" : "primary";

  return <section aria-labelledby="support-targets-title">
    <h2 id="support-targets-title">Дежурные адресаты поддержки</h2>
    <p>Окно: ежедневно 10:00–22:00 МСК. Резервная смена появится только после назначения реального сотрудника.</p>
    <p>Кабинет администратора получает просроченные обращения. Email ставится в очередь после записи события; отправка и её исход проверяются отдельно. Telegram пока не подключён.</p>
    <form onSubmit={(event) => void refresh(event)}>
      <label>Код 2FA для управления адресатами
        <input type="password" inputMode="numeric" autoComplete="one-time-code" value={code}
          onChange={(event) => setCode(event.target.value)} minLength={6} maxLength={8} />
      </label>
      <button type="submit" disabled={busy}>Загрузить адресатов</button>
    </form>
    {error ? <p role="alert">{error}</p> : null}
    {notice ? <p role="status">{notice}</p> : null}
    {targets ? <>
      <p>Email транспорт: {targets.email_transport_ready ? "настроен" : "не настроен"}. Telegram: отключён.</p>
      <div style={{ display: "flex", flexWrap: "wrap", gap: "0.75rem" }}>
        <label>Сотрудник
          <select aria-label="Сотрудник" value={staffId} onChange={(event) => { setStaffId(event.target.value); setLevel("administrator"); }}>
            <option value="">Выберите сотрудника</option>
            {staff.map((person) => <option key={person.id} value={person.id}>
              {person.name} · {person.role === "administrator" ? "администратор" : "оператор"}
            </option>)}
          </select>
        </label>
        <label>Уровень
          <select aria-label="Уровень" value={effectiveLevel}
            onChange={(event) => setLevel(event.target.value as typeof level)}>
            {allowedLevels.map((value) => <option key={value} value={value}>
              {value === "administrator" ? "Администратор" : value === "primary" ? "Основной" : "Резервный"}
            </option>)}
          </select>
        </label>
        <label>Канал
          <select aria-label="Канал" value={channel} onChange={(event) => setChannel(event.target.value as typeof channel)}>
            <option value="cabinet">Кабинет</option><option value="email">Подтверждённая почта сотрудника</option>
          </select>
        </label>
      </div>
      <button type="button" disabled={busy || !selected} onClick={() => {
        if (selected) void configure(selected.id, channel, effectiveLevel, true);
      }}>Включить адресата</button>
      <ul>{targets.items.map((item) => <li key={item.id}>
        {staff.find((person) => person.id === item.recipient_user_id)?.name || "Сотрудник"} · {item.escalation_level} · {item.channel} · {item.active ? "включён" : "выключен"}
        {item.active ? <button type="button" disabled={busy} onClick={() => void configure(
          item.recipient_user_id, item.channel,
          item.escalation_level, false,
        )}>Выключить</button> : null}
      </li>)}</ul>
    </> : null}
  </section>;
}
