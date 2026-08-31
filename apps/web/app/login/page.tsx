"use client";

import { FormEvent, useState } from "react";
import { useRouter } from "next/navigation";
import { BrandLockup } from "@/components/BrandLockup";
import { api, createOrgWithConfirm, setActiveOrg, setToken } from "@/lib/api";
import { safeNext } from "@/lib/next";

export default function LoginPage() {
  const router = useRouter();
  const [mode, setMode] = useState<"login" | "register" | "recover">("login");
  const [error, setError] = useState("");
  const [pending, setPending] = useState(false);
  const [notice, setNotice] = useState("");
  const [selectedRole, setSelectedRole] = useState("customer");

  async function onSubmit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setError("");
    setNotice("");
    setPending(true);
    const form = new FormData(e.currentTarget);
    try {
      if (mode === "recover") {
        await api("/auth/recover", {
          method: "POST",
          body: JSON.stringify({ email: String(form.get("email") || "") }),
        });
        setNotice("Если аккаунт существует, инструкция для восстановления будет отправлена на указанную почту.");
        return;
      }
      const path = mode === "login" ? "/auth/login" : "/auth/register";
      const payload: Record<string, unknown> = {
        email: String(form.get("email") || ""),
        password: String(form.get("password") || ""),
      };
      if (mode === "register") {
        payload.full_name = String(form.get("full_name") || "Пользователь");
        payload.accept_offer = form.get("accept_offer") === "on";
        payload.accept_privacy = form.get("accept_privacy") === "on";
        payload.marketing_opt_in = form.get("marketing_opt_in") === "on";
      }
      const res = await api<{ token: string; is_platform_admin?: boolean }>(path, {
        method: "POST",
        body: JSON.stringify(payload),
      });
      setToken(res.token);
      if (res.is_platform_admin) localStorage.setItem("booker.admin", "1");
      else localStorage.removeItem("booker.admin");
      if (mode === "register") {
        const kind = String(form.get("kind") || "customer");
        const org = await createOrgWithConfirm({
          name: String(payload.full_name || "Пользователь"),
          kind,
          city: "Москва",
        });
        setActiveOrg(org.id);
      } else {
        const me = await api<{ active_organization_id?: string }>("/me");
        if (me.active_organization_id) setActiveOrg(me.active_organization_id);
      }
      router.push(safeNext(new URLSearchParams(window.location.search).get("next")));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Ошибка входа");
    } finally {
      setPending(false);
    }
  }

  return (
    <main>
      <p className="brand-lockup-wrap">
        <BrandLockup />
      </p>
      <p className="kicker">
        {mode === "recover" ? "Восстановление доступа" : mode === "login" ? "Backstage Control Room" : "Новый аккаунт"}
      </p>
      <h1>
        {mode === "recover"
          ? "Вернём доступ к кабинету"
          : mode === "login"
            ? "Войти в Букер"
            : "Создать кабинет"}
      </h1>
      {mode === "login" ? (
        <details className="timeline">
          <summary>Демонстрационные аккаунты</summary>
          <p>Пароль для демовхода: password1. Код подтверждения в Deal Room: 123456.</p>
          <p style={{ display: "flex", gap: 8, flexWrap: "wrap", marginTop: 8 }}>
            {(
              [
                ["customer@booker.test", "Заказчик"],
                ["artist@booker.test", "Исполнитель"],
                ["admin@booker.test", "Оператор"],
              ] as const
            ).map(([email, label]) => (
              <button
                key={email}
                type="button"
                className="secondary"
                onClick={() => {
                  const form = document.querySelector<HTMLFormElement>("form.card");
                  const mail = form?.querySelector<HTMLInputElement>('input[name="email"]');
                  const pass = form?.querySelector<HTMLInputElement>('input[name="password"]');
                  if (mail) mail.value = email;
                  if (pass) pass.value = "password1";
                }}
              >
                {label}
              </button>
            ))}
          </p>
        </details>
      ) : (
        <p className="timeline">Выберите роль — мы настроим кабинет и первый сценарий под ваши задачи.</p>
      )}
      <form className="card" style={{ display: "grid", gap: 12, maxWidth: 420 }} onSubmit={onSubmit}>
        {mode === "register" ? (
          <>
            <label>
              Имя
              <input name="full_name" required />
            </label>
            <fieldset className="role-picker">
              <legend>Роль</legend>
              <input type="hidden" name="kind" value={selectedRole} />
              {[
                ["customer", "Заказчик", "Ищу артиста или площадку"],
                ["artist", "Артист / менеджер", "Управляю датами и предложениями"],
                ["venue", "Площадка", "Размещаю пространство и слоты"],
              ].map(([value, title, description]) => (
                <button
                  key={value}
                  type="button"
                  className={`role-option ${selectedRole === value ? "on" : ""}`}
                  aria-pressed={selectedRole === value}
                  onClick={() => setSelectedRole(value)}
                >
                  <span><strong>{title}</strong><small>{description}</small></span>
                  <span aria-hidden>{selectedRole === value ? "✓" : ""}</span>
                </button>
              ))}
            </fieldset>
          </>
        ) : null}
        <label>
          Email
          <input name="email" type="email" autoComplete="username" required />
        </label>
        {mode !== "recover" ? (
          <label>
            Пароль
            <input name="password" type="password" autoComplete="current-password" required minLength={8} />
          </label>
        ) : null}
        {mode === "register" ? (
          <>
            <label className="unknown">
              <input name="accept_offer" type="checkbox" required />
              Принимаю <a href="/legal/offer">оферту</a> и правила использования сервиса.
            </label>
            <label className="unknown">
              <input name="accept_privacy" type="checkbox" required />
              Согласен с <a href="/legal/privacy">политикой обработки персональных данных</a>.
            </label>
            <label className="unknown">
              <input name="marketing_opt_in" type="checkbox" />
              Получать новости продукта и специальные предложения. Необязательно.
            </label>
          </>
        ) : null}
        {error ? <p style={{ color: "var(--danger)" }}>{error}</p> : null}
        {notice ? <p className="timeline">{notice}</p> : null}
        <button type="submit" disabled={pending}>
          {pending ? "Обрабатываем…" : mode === "recover" ? "Отправить инструкцию" : mode === "login" ? "Войти" : "Создать аккаунт"}
        </button>
      </form>
      <p style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
        <button type="button" className="secondary" onClick={() => setMode(mode === "login" ? "register" : "login")}>
          {mode === "login" ? "Создать аккаунт" : "Вернуться ко входу"}
        </button>
        {mode === "login" ? (
          <button type="button" className="secondary" onClick={() => setMode("recover")}>
            Забыли пароль?
          </button>
        ) : null}
      </p>
    </main>
  );
}
