"use client";

import React, { useEffect, useState, type FormEvent } from "react";
import Link from "next/link";
import { api, ApiError } from "@/lib/api";
import { loginHref } from "@/lib/next";

type SupportOperator = {
  id: string;
  email: string;
  totp_enabled: boolean;
  email_verified: boolean;
};

type RoleChange = {
  id: string;
  is_support_operator: boolean;
  totp_enabled: boolean;
  idempotent: boolean;
};

function stepUpHeaders(totp: string): Headers {
  const headers = new Headers();
  if (totp.trim()) headers.set("X-Booker-TOTP", totp.trim());
  return headers;
}

export async function listSupportOperators(totp = ""): Promise<SupportOperator[]> {
  const result = await api<{ items: SupportOperator[] }>("/admin/support/operators", {
    headers: stepUpHeaders(totp),
    cache: "no-store",
  });
  return result.items;
}

export function setSupportOperator(email: string, enabled: boolean, totp: string): Promise<RoleChange> {
  return api<RoleChange>("/admin/support/operators", {
    method: "POST",
    headers: stepUpHeaders(totp),
    body: JSON.stringify({ email: email.trim().toLowerCase(), enabled }),
  });
}

function errorMessage(error: unknown): string {
  if (error instanceof ApiError) {
    if (error.status === 401) return "Сеанс истёк. Войдите снова как администратор.";
    if (error.status === 403) return "Нужен действующий код TOTP администратора и право управления операторами.";
    if (error.status === 404) return "Аккаунт с этим email не найден. Сначала зарегистрируйте пользователя.";
    if (error.status === 409) return error.message;
  }
  return "Не удалось выполнить действие. Проверьте соединение и попробуйте ещё раз.";
}

export default function SupportOperatorManagement({ totpEnabled }: { totpEnabled: boolean }) {
  const [operators, setOperators] = useState<SupportOperator[] | null>(null);
  const [email, setEmail] = useState("");
  const [totp, setTotp] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");

  useEffect(() => {
    if (!totpEnabled) return;
    let active = true;
    void listSupportOperators().then((items) => {
      if (active) setOperators(items);
    }).catch((failure: unknown) => {
      if (active) setError(errorMessage(failure));
    });
    return () => { active = false; };
  }, [totpEnabled]);

  async function refresh(event: FormEvent) {
    event.preventDefault();
    if (busy) return;
    setBusy(true);
    setError("");
    setNotice("");
    const code = totp.trim();
    setTotp("");
    try {
      setOperators(await listSupportOperators(code));
    } catch (failure) {
      if (failure instanceof ApiError && (failure.status === 401 || failure.status === 403)) setOperators(null);
      setError(errorMessage(failure));
    } finally {
      setBusy(false);
    }
  }

  async function changeRole(targetEmail: string, enabled: boolean) {
    if (busy || !totp.trim()) return;
    if (!enabled && !window.confirm(`Снять роль оператора поддержки у ${targetEmail}? Его текущие сеансы завершатся.`)) return;
    setBusy(true);
    setError("");
    setNotice("");
    const code = totp.trim();
    setTotp("");
    try {
      const result = await setSupportOperator(targetEmail, enabled, code);
      if (enabled) setEmail("");
      setNotice(result.idempotent
        ? "Роль уже была в нужном состоянии."
        : enabled
          ? result.totp_enabled
            ? "Роль выдана. Оператору нужно войти заново."
            : "Роль выдана. Оператору нужно настроить TOTP и войти заново."
          : "Роль снята. Сеансы оператора завершены.");
      setOperators(await listSupportOperators(code));
    } catch (failure) {
      if (failure instanceof ApiError && (failure.status === 401 || failure.status === 403)) setOperators(null);
      setError(errorMessage(failure));
    } finally {
      setBusy(false);
    }
  }

  function grant(event: FormEvent) {
    event.preventDefault();
    void changeRole(email, true);
  }

  return (
    <section aria-labelledby="support-operators-title">
      <h2 id="support-operators-title">Операторы поддержки</h2>
      <p className="timeline">Роль даёт доступ к обращениям поддержки. Платежи, возвраты и решения по спорам остаются в отдельном административном контуре.</p>
      {!totpEnabled ? (
        <p role="status">Для управления ролями настройте TOTP администратора. <Link href={`${loginHref("/admin")}&enroll=1`}>Перейти к настройке</Link>.</p>
      ) : (
        <>
          <form onSubmit={refresh} style={{ display: "grid", gap: 8, maxWidth: 360 }}>
            <label>
              Код TOTP администратора
              <input type="password" inputMode="numeric" autoComplete="one-time-code" minLength={6} maxLength={8}
                value={totp} onChange={(event) => setTotp(event.target.value)} />
            </label>
            <button type="submit" className="secondary" disabled={busy}>Обновить список</button>
          </form>
          {error ? <p role="alert">{error}</p> : null}
          {notice ? <p role="status">{notice}</p> : null}
          {operators === null ? <p className="timeline">Введите код TOTP и обновите список операторов.</p> : (
            <>
              <ul style={{ display: "grid", gap: 12, paddingLeft: 20 }}>
                {operators.map((operator) => (
                  <li key={operator.id}>
                    <strong>{operator.email}</strong>{" · "}
                    {operator.totp_enabled ? "TOTP настроен" : "Нужна настройка TOTP перед работой"}{" · "}
                    {operator.email_verified ? "email подтверждён" : "email не подтверждён"}{" "}
                    <button type="button" className="secondary" disabled={busy || !totp.trim()}
                      onClick={() => void changeRole(operator.email, false)}>Снять роль</button>
                  </li>
                ))}
              </ul>
              {operators.length === 0 ? <p>Операторов поддержки пока нет.</p> : null}
            </>
          )}
          <form onSubmit={grant} style={{ display: "grid", gap: 8, maxWidth: 360 }}>
            <label>
              Email зарегистрированного пользователя
              <input type="email" autoComplete="email" value={email} onChange={(event) => setEmail(event.target.value)} required />
            </label>
            <p className="timeline">Перед выдачей роли пользователь должен подтвердить email. Для работы с обращениями ему понадобится TOTP.</p>
            <button type="submit" disabled={busy || !totp.trim()}>Выдать роль оператора</button>
          </form>
        </>
      )}
    </section>
  );
}
