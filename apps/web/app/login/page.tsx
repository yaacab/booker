"use client";

import { FormEvent, Fragment, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { BrandLockup } from "@/components/BrandLockup";
import { api, createOrgWithConfirm, setActiveOrg, setToken } from "@/lib/api";
import { cabinetPathForKind } from "@/lib/cabinetRoutes";
import { safeNext } from "@/lib/next";
import { getPublicLegalPack, legalDocumentHref, legalDocumentLabel, registrationLegalState, type LegalPack } from "@/lib/legalPack";

function generateTotpSecret(): string {
  const alphabet = "ABCDEFGHIJKLMNOPQRSTUVWXYZ234567";
  const bytes = new Uint8Array(20);
  window.crypto.getRandomValues(bytes);
  let value = 0;
  let bits = 0;
  let secret = "";
  for (const byte of bytes) {
    value = (value << 8) | byte;
    bits += 8;
    while (bits >= 5) {
      secret += alphabet[(value >>> (bits - 5)) & 31];
      bits -= 5;
    }
  }
  return secret;
}

export default function LoginPage() {
  const router = useRouter();
  const [mode, setMode] = useState<"login" | "register" | "recover" | "reset" | "enroll" | "staff-recover" | "staff-recovery-codes" | "verify" | "workspace">("login");
  const [resetToken, setResetToken] = useState("");
  const [verificationToken, setVerificationToken] = useState("");
  const [verificationEmail, setVerificationEmail] = useState("");
  const [workspaceName, setWorkspaceName] = useState("");
  const [enrollStep, setEnrollStep] = useState<"challenge" | "confirm" | "recovery">("challenge");
  const [operatorEnrollment, setOperatorEnrollment] = useState(false);
  const [enrollEmail, setEnrollEmail] = useState("");
  const [enrollSecret, setEnrollSecret] = useState("");
  const [recoveryCodes, setRecoveryCodes] = useState<string[]>([]);
  const [recoverySaved, setRecoverySaved] = useState(false);
  const [error, setError] = useState("");
  const [pending, setPending] = useState(false);
  const [notice, setNotice] = useState("");
  const [selectedRole, setSelectedRole] = useState("customer");
  const [legalPack, setLegalPack] = useState<LegalPack | null>(null);
  const [legalLoading, setLegalLoading] = useState(true);

  useEffect(() => {
    const readLocation = () => {
      setOperatorEnrollment(new URLSearchParams(window.location.search).get("next") === "/operator");
      const verification = new URLSearchParams(window.location.hash.slice(1)).get("verify");
      if (verification) {
        setVerificationToken(verification);
        setMode("verify");
        window.history.replaceState(null, "", window.location.pathname + window.location.search);
        return;
      }
      const token = new URLSearchParams(window.location.search).get("reset");
      if (token) {
        setResetToken(token);
        setMode("reset");
      } else if (new URLSearchParams(window.location.search).get("enroll") === "1") {
        setOperatorEnrollment(new URLSearchParams(window.location.search).get("next") === "/operator");
        setToken(null);
        localStorage.removeItem("booker.admin");
        setMode("enroll");
      }
    };
    readLocation();
    window.addEventListener("hashchange", readLocation);
    return () => window.removeEventListener("hashchange", readLocation);
  }, []);

  async function verifyEmail(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setError("");
    setNotice("");
    setPending(true);
    const form = new FormData(e.currentTarget);
    const email = String(form.get("email") || "").trim();
    const password = String(form.get("password") || "");
    try {
      if (!verificationToken) {
        await api("/auth/email-verification/request", {
          method: "POST", body: JSON.stringify({ email, password }),
        });
        setVerificationEmail(email);
        setNotice("Если данные подходят, новое письмо с подтверждением отправлено. Проверьте почту.");
        return;
      }
      const totp = String(form.get("totp") || "").trim();
      setToken(null);
      localStorage.removeItem("booker.admin");
      const login = await api<{ token: string; is_platform_admin?: boolean; is_support_operator?: boolean }>("/auth/login", {
        method: "POST",
        body: JSON.stringify({ email, password, ...(totp ? { totp } : {}) }),
      });
      setToken(login.token);
      if (login.is_platform_admin) localStorage.setItem("booker.admin", "1");
      await api("/auth/email-verification/confirm", {
        method: "POST", body: JSON.stringify({ token: verificationToken }),
      });
      const me = await api<{ is_support_operator?: boolean; organizations?: { id: string; kind: string }[] }>("/me");
      setVerificationToken("");
      if (me.is_support_operator || login.is_support_operator) {
        router.push("/operator");
        return;
      }
      const org = me.organizations?.[0];
      if (org) {
        setActiveOrg(org.id);
        router.push(cabinetPathForKind(org.kind));
      } else {
        setMode("workspace");
        setNotice("Email подтверждён. Теперь создайте своё рабочее пространство.");
      }
    } catch (err) {
      if (verificationToken) {
        setToken(null);
        localStorage.removeItem("booker.admin");
      }
      setError(err instanceof Error ? err.message : "Не удалось подтвердить email. Повторите попытку.");
    } finally {
      setPending(false);
    }
  }

  async function createVerifiedWorkspace(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setError("");
    setPending(true);
    const form = new FormData(e.currentTarget);
    const kind = String(form.get("kind") || "customer");
    try {
      const org = await createOrgWithConfirm({
        name: String(form.get("name") || "").trim(), kind, city: "Москва",
      });
      setActiveOrg(org.id);
      const rawNext = new URLSearchParams(window.location.search).get("next");
      const roleCabinet = cabinetPathForKind(kind);
      const next = safeNext(rawNext, roleCabinet);
      router.push(!rawNext || next === "/cabinet" ? roleCabinet : next);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Не удалось создать рабочее пространство.");
    } finally {
      setPending(false);
    }
  }

  function leaveEnrollment() {
    setEnrollEmail("");
    setEnrollSecret("");
    setRecoveryCodes([]);
    setRecoverySaved(false);
    setEnrollStep("challenge");
    setError("");
    setNotice("");
    const url = new URL(window.location.href);
    url.searchParams.delete("enroll");
    window.history.replaceState(null, "", url.pathname + url.search);
    setMode("login");
  }

  async function requestEnrollmentChallenge(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setError("");
    setNotice("");
    setPending(true);
    const form = new FormData(e.currentTarget);
    const email = String(form.get("email") || "").trim();
    const password = String(form.get("password") || "");
    try {
      const secret = generateTotpSecret();
      await api<{ ok: boolean }>("/auth/admin-totp/challenge", {
        method: "POST",
        body: JSON.stringify({ email, password }),
      });
      setEnrollEmail(email);
      setEnrollSecret(secret);
      setEnrollStep("confirm");
      setNotice("Если данные подходят, код подтверждения отправлен на почту. Проверьте письмо.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Не удалось запросить подтверждение. Повторите попытку.");
    } finally {
      setPending(false);
    }
  }

  async function confirmEnrollment(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setError("");
    setPending(true);
    const form = new FormData(e.currentTarget);
    try {
      const result = await api<{ recovery_codes: string[] }>("/auth/admin-totp/confirm", {
        method: "POST",
        body: JSON.stringify({
          email: enrollEmail,
          password: String(form.get("password") || ""),
          proof: String(form.get("proof") || "").trim(),
          secret: enrollSecret,
          code: String(form.get("code") || "").trim(),
        }),
      });
      setToken(null);
      localStorage.removeItem("booker.admin");
      setEnrollSecret("");
      setRecoveryCodes(result.recovery_codes);
      setRecoverySaved(false);
      setEnrollStep("recovery");
      setNotice("Второй фактор включён. Сохраните резервные коды до перехода ко входу.");
    } catch (err) {
      const message = err instanceof Error ? err.message : "Не удалось подтвердить второй фактор";
      setError(message === "Подтверждение недействительно"
        ? "Подтверждение недействительно. Проверьте пароль, код из письма и код приложения. Если письмо истекло, запросите новое."
        : message);
    } finally {
      setPending(false);
    }
  }

  async function recoverStaffTotp(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setError("");
    setPending(true);
    const form = new FormData(e.currentTarget);
    try {
      const result = await api<{ recovery_codes: string[] }>("/auth/admin-totp/recover", {
        method: "POST",
        body: JSON.stringify({
          email: String(form.get("email") || "").trim(),
          password: String(form.get("password") || ""),
          recovery_code: String(form.get("recovery_code") || "").trim(),
          secret: enrollSecret,
          code: String(form.get("code") || "").trim(),
        }),
      });
      setToken(null);
      localStorage.removeItem("booker.admin");
      setEnrollSecret("");
      setRecoveryCodes(result.recovery_codes);
      setRecoverySaved(false);
      setMode("staff-recovery-codes");
      setNotice("Доступ восстановлен. Сохраните новые резервные коды и войдите с новым Authenticator.");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Не удалось восстановить доступ");
    } finally {
      setPending(false);
    }
  }

  useEffect(() => {
    let active = true;
    void getPublicLegalPack().then((pack) => {
      if (active) {
        setLegalPack(pack);
        setLegalLoading(false);
      }
    });
    return () => { active = false; };
  }, []);

  async function onSubmit(e: FormEvent<HTMLFormElement>) {
    e.preventDefault();
    setError("");
    setNotice("");
    setPending(true);
    const form = new FormData(e.currentTarget);
    try {
      if (mode === "reset") {
        const totp = String(form.get("totp") || "").trim();
        await api("/auth/recover/confirm", {
          method: "POST",
          body: JSON.stringify({
            token: resetToken,
            password: String(form.get("password") || ""),
            ...(totp ? { totp } : {}),
          }),
        });
        setNotice("Пароль обновлён. Войдите с новым паролем.");
        setMode("login");
        return;
      }
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
      if (mode === "login") {
        const totp = String(form.get("totp") || "").trim();
        if (totp) payload.totp = totp;
        setToken(null);
        localStorage.removeItem("booker.admin");
      }
      if (mode === "register") {
        const shownLegal = registrationLegalState(legalPack);
        if (!shownLegal.available) throw new Error("Регистрация пока недоступна: сервер не подтвердил юридический пакет.");
        const freshPack = await getPublicLegalPack();
        const freshLegal = registrationLegalState(freshPack);
        if (!freshLegal.available) {
          setLegalPack(freshPack);
          throw new Error("Регистрация пока недоступна: сервер не подтвердил юридический пакет.");
        }
        if (freshPack?.pack_version !== legalPack?.pack_version ||
            freshPack?.acceptance_effect !== legalPack?.acceptance_effect ||
            JSON.stringify(freshLegal.accepted_documents) !== JSON.stringify(shownLegal.accepted_documents)) {
          setLegalPack(freshPack);
          throw new Error("Редакция документов изменилась. Ознакомьтесь с ней и подтвердите отметки заново.");
        }
        payload.full_name = String(form.get("full_name") || "Пользователь");
        payload.accept_offer = form.get("accept_offer") === "on";
        payload.accept_privacy = form.get("accept_privacy") === "on";
        payload.accept_processing = form.get("accept_consent_texts") === "on";
        payload.marketing_opt_in = form.get("marketing_opt_in") === "on";
        payload.accepted_documents = shownLegal.accepted_documents;
        payload.draft_test_acknowledgement = shownLegal.draftTest && form.get("draft_test_acknowledgement") === "on";
      }
      const res = await api<{
        token: string;
        is_platform_admin?: boolean;
        is_support_operator?: boolean;
        email_verification_required?: boolean;
        email_verification_delivery?: string;
      }>(path, {
        method: "POST",
        body: JSON.stringify(payload),
      });
      if (mode === "register") setToken(null);
      setToken(res.token);
      if (res.is_platform_admin) localStorage.setItem("booker.admin", "1");
      else localStorage.removeItem("booker.admin");
      if (mode === "register") {
        const kind = String(form.get("kind") || "customer");
        if (res.email_verification_required) {
          setVerificationEmail(String(payload.email || ""));
          setWorkspaceName(String(payload.full_name || ""));
          setSelectedRole(kind);
          setMode("verify");
          setNotice(res.email_verification_delivery === "sent"
            ? "Аккаунт создан. Проверьте почту и подтвердите адрес перед созданием рабочего пространства."
            : "Аккаунт создан, но доставка письма пока не подтверждена. Повторите запрос, когда почта будет доступна.");
          return;
        }
        const org = await createOrgWithConfirm({
          name: String(payload.full_name || "Пользователь"),
          kind,
          city: "Москва",
        });
        setActiveOrg(org.id);
        const rawNext = new URLSearchParams(window.location.search).get("next");
        const roleCabinet = cabinetPathForKind(kind);
        const next = safeNext(rawNext, roleCabinet);
        router.push(!rawNext || next === "/cabinet" ? roleCabinet : next);
        return;
      }
      const me = await api<{
        organizations?: { id: string; kind: string }[];
        active_organization_id?: string;
        email_verified?: boolean;
        email_verification_required?: boolean;
        is_support_operator?: boolean;
      }>("/me");
      if (me.email_verification_required && !me.email_verified) {
        setVerificationEmail(String(payload.email || ""));
        setMode("verify");
        setNotice("Подтвердите email перед созданием нового рабочего пространства.");
        return;
      }
      if (me.is_support_operator || res.is_support_operator) {
        router.push("/operator");
        return;
      }
      if (res.is_platform_admin) {
        const rawNext = new URLSearchParams(window.location.search).get("next");
        router.push(safeNext(rawNext, "/admin"));
        return;
      }
      if (!me.organizations?.length) {
        setMode("workspace");
        setNotice("Создайте рабочее пространство, чтобы продолжить.");
        return;
      }
      const activeOrgId = me.active_organization_id || me.organizations?.[0]?.id;
      if (activeOrgId) setActiveOrg(activeOrgId);
      const org = me.organizations?.find((o) => o.id === activeOrgId) || me.organizations?.[0];
      const rawNext = new URLSearchParams(window.location.search).get("next");
      const next = safeNext(rawNext);
      if (!rawNext || next === "/cabinet") {
        router.push(cabinetPathForKind(org?.kind || "customer"));
      } else {
        router.push(next);
      }
    } catch (err) {
      if (mode === "login") {
        setToken(null);
        localStorage.removeItem("booker.admin");
      }
      const message = err instanceof Error ? err.message : "Ошибка входа";
      setError(
        mode === "login" && message === "Нужен код второго фактора"
          ? "Нужен шестизначный код из приложения-аутентификатора. Введите его и повторите вход."
          : mode === "reset" && message === "Нужен действующий код второго фактора"
            ? "Для сброса пароля администратора нужен действующий шестизначный код из приложения-аутентификатора."
            : message,
      );
    } finally {
      setPending(false);
    }
  }

  const heading =
    mode === "enroll"
      ? operatorEnrollment ? "Настроить второй фактор оператора" : "Настроить второй фактор администратора"
      : mode === "staff-recover" || mode === "staff-recovery-codes"
      ? "Восстановить второй фактор"
      : mode === "verify"
      ? "Подтвердить email"
      : mode === "workspace"
      ? "Создать рабочее пространство"
      : mode === "reset"
      ? "Задайте новый пароль"
      : mode === "recover"
        ? "Вернём доступ к кабинету"
        : mode === "login"
          ? "Войти в Букер"
          : "Создать кабинет";

  const kicker =
    mode === "enroll"
      ? "Защита входа"
      : mode === "staff-recover" || mode === "staff-recovery-codes"
      ? "Резервный доступ"
      : mode === "verify"
      ? "Подтверждение адреса"
      : mode === "workspace"
      ? "Первый шаг в Букере"
      : mode === "reset"
      ? "Подтверждение восстановления"
      : mode === "recover"
        ? "Восстановление доступа"
        : mode === "login"
          ? "Ваше пространство событий"
          : "Новый аккаунт";

  const legalState = registrationLegalState(legalPack);
  const legalUnavailable = legalLoading || !legalState.available;
  const legalConsentKey = `${legalPack?.pack_version || "none"}:${legalPack?.acceptance_effect || "none"}:${JSON.stringify(legalState.accepted_documents)}`;

  return (
    <main>
      <p className="brand-lockup-wrap">
        <BrandLockup />
      </p>
      <p className="kicker">{kicker}</p>
      <h1>{heading}</h1>
      {mode === "enroll" ? (
        <p className="timeline">Настройка доступна до первого входа. Потребуются пароль, подтверждение из письма и приложение-аутентификатор.</p>
      ) : mode === "staff-recover" ? (
        <p className="timeline">Используйте заранее сохранённый одноразовый код, пароль и новый код из приложения-аутентификатора. Для администратора при нескольких администраторах требуется отдельная проверка двумя уполномоченными лицами.</p>
      ) : mode === "verify" ? (
        <p className="timeline">Перейдите по ссылке из письма, затем войдите в свой аккаунт для подтверждения адреса. Если письмо не пришло, запросите новое.</p>
      ) : mode === "workspace" ? (
        <p className="timeline">Выберите роль и назовите рабочее пространство. Права на профиль и календарь проверяются отдельно.</p>
      ) : mode === "register" ? (
        <>
          <p className="timeline">Выберите роль — мы настроим кабинет и первый сценарий под ваши задачи.</p>
          <p className="legal-banner" role="status">
            {legalLoading ? "Проверяем юридический пакет…" : legalUnavailable
              ? "Регистрация временно недоступна: действующий пакет документов не подтверждён сервером. Вход и восстановление доступа работают."
              : legalState.draftTest
                ? `Тестовая регистрация: пакет ${legalPack?.pack_version} — черновик. Отметки подтверждают ознакомление в тестовой среде и не являются юридическим акцептом.`
                : `Пакет ${legalPack?.pack_version} опубликован. Перед регистрацией ознакомьтесь с обязательными документами.`}
          </p>
        </>
      ) : mode === "reset" ? (
        <p className="timeline">Введите новый пароль для аккаунта.</p>
      ) : mode === "recover" ? (
        <p className="timeline">Укажите email — отправим инструкцию, если аккаунт существует.</p>
      ) : legalUnavailable ? (
        <p className="timeline">Регистрация временно недоступна: юридический пакет не подтверждён сервером.</p>
      ) : null}
      {mode === "staff-recover" ? (
        <form className="card surface-glass" style={{ display: "grid", gap: 12, maxWidth: 440 }} onSubmit={recoverStaffTotp}>
          <label>Email<input name="email" type="email" autoComplete="username" required /></label>
          <label>Пароль<input name="password" type="password" autoComplete="current-password" required /></label>
          <label>Сохранённый резервный код<input name="recovery_code" autoComplete="off" minLength={24} maxLength={40} required /></label>
          <p className="timeline">Добавьте новый аккаунт Букера в приложение-аутентификатор с этим секретом. После подтверждения старый Authenticator и старые коды перестанут работать.</p>
          <label htmlFor="staff-new-totp-secret">Новый секрет TOTP</label>
          <input id="staff-new-totp-secret" value={enrollSecret} readOnly autoComplete="off" spellCheck={false} />
          <label>Текущий код нового приложения<input name="code" inputMode="numeric" autoComplete="one-time-code" pattern="[0-9]{6}" minLength={6} maxLength={6} required /></label>
          {error ? <p role="alert" style={{ color: "var(--danger)" }}>{error}</p> : null}
          <button type="submit" disabled={pending}>{pending ? "Проверяем…" : "Восстановить доступ"}</button>
        </form>
      ) : mode === "staff-recovery-codes" ? (
        <section className="card surface-glass" style={{ display: "grid", gap: 12, maxWidth: 480 }} aria-label="Новые резервные коды">
          <p role="status" className="timeline">{notice} Каждый код работает один раз и больше не появится на этой странице.</p>
          <label htmlFor="new-staff-recovery-codes">Новые резервные коды</label>
          <textarea id="new-staff-recovery-codes" readOnly rows={10} value={recoveryCodes.join("\n")} autoComplete="off" spellCheck={false} />
          <label><input type="checkbox" checked={recoverySaved} onChange={(event) => setRecoverySaved(event.target.checked)} /> Я сохранил новые коды вне Букера</label>
          <button type="button" disabled={!recoverySaved} onClick={() => { setRecoveryCodes([]); setRecoverySaved(false); setMode("login"); setNotice(""); }}>Перейти ко входу</button>
        </section>
      ) : mode === "verify" ? (
        <form className="card surface-glass" style={{ display: "grid", gap: 12, maxWidth: 420 }} onSubmit={verifyEmail}>
          <label>Email<input name="email" type="email" autoComplete="username" defaultValue={verificationEmail} required /></label>
          <label>Пароль<input name="password" type="password" autoComplete="current-password" required /></label>
          {verificationToken ? (
            <label>Код из приложения, если включён второй фактор
              <input name="totp" inputMode="numeric" autoComplete="one-time-code" pattern="[0-9]{6}" minLength={6} maxLength={6} />
            </label>
          ) : null}
          {notice ? <p role="status" className="timeline">{notice}</p> : null}
          {error ? <p role="alert" style={{ color: "var(--danger)" }}>{error}</p> : null}
          <button type="submit" disabled={pending}>{pending ? "Проверяем…" : verificationToken ? "Подтвердить адрес" : "Запросить новое письмо"}</button>
        </form>
      ) : mode === "workspace" ? (
        <form className="card surface-glass" style={{ display: "grid", gap: 12, maxWidth: 420 }} onSubmit={createVerifiedWorkspace}>
          <label>Название рабочего пространства
            <input name="name" defaultValue={workspaceName} required minLength={2} />
          </label>
          <label>Роль
            <select name="kind" defaultValue={selectedRole}>
              <option value="customer">Заказчик</option>
              <option value="artist">Артист / менеджер</option>
              <option value="venue">Площадка</option>
            </select>
          </label>
          {notice ? <p role="status" className="timeline">{notice}</p> : null}
          {error ? <p role="alert" style={{ color: "var(--danger)" }}>{error}</p> : null}
          <button type="submit" disabled={pending}>{pending ? "Создаём…" : "Создать пространство"}</button>
        </form>
      ) : mode === "enroll" ? (
        enrollStep === "challenge" ? (
          <form className="card surface-glass" style={{ display: "grid", gap: 12, maxWidth: 420 }} onSubmit={requestEnrollmentChallenge}>
            <label>{operatorEnrollment ? "Email оператора" : "Email администратора"}<input name="email" type="email" autoComplete="username" required /></label>
            <label>{operatorEnrollment ? "Пароль оператора" : "Пароль администратора"}<input name="password" type="password" autoComplete="current-password" required /></label>
            {error ? <p role="alert" style={{ color: "var(--danger)" }}>{error}</p> : null}
            <button type="submit" disabled={pending}>{pending ? "Запрашиваем…" : "Получить подтверждение по почте"}</button>
          </form>
        ) : enrollStep === "confirm" ? (
          <form className="card surface-glass" style={{ display: "grid", gap: 12, maxWidth: 420 }} onSubmit={confirmEnrollment}>
            {notice ? <p role="status" className="timeline">{notice}</p> : null}
            <p className="timeline">Почта: {enrollEmail}. Добавьте новый аккаунт вручную в приложение-аутентификатор и укажите секрет ниже. Секрет хранится только до ухода с этой страницы.</p>
            <label htmlFor="enroll-secret">Секрет TOTP для приложения</label>
            <input id="enroll-secret" value={enrollSecret} readOnly autoComplete="off" spellCheck={false} />
            <label htmlFor="enroll-proof">Код подтверждения из письма</label>
            <input id="enroll-proof" name="proof" autoComplete="off" minLength={32} maxLength={128} required />
            <label htmlFor="enroll-password">Повторите пароль {operatorEnrollment ? "оператора" : "администратора"}</label>
            <input id="enroll-password" name="password" type="password" autoComplete="current-password" required />
            <label htmlFor="enroll-code">Текущий код из приложения</label>
            <input id="enroll-code" name="code" inputMode="numeric" autoComplete="one-time-code" pattern="[0-9]{6}" minLength={6} maxLength={6} required />
            {error ? <p role="alert" style={{ color: "var(--danger)" }}>{error}</p> : null}
            <button type="submit" disabled={pending}>{pending ? "Подтверждаем…" : "Включить второй фактор"}</button>
            <button type="button" className="secondary" disabled={pending} onClick={() => { setEnrollSecret(""); setEnrollStep("challenge"); setError(""); setNotice(""); }}>Запросить новое подтверждение</button>
          </form>
        ) : (
          <section className="card surface-glass" style={{ display: "grid", gap: 12, maxWidth: 480 }} aria-label="Резервные коды входа">
            <p role="status" className="timeline">{notice} Каждый код работает один раз. Они больше не появятся в кабинете и не отправляются по почте.</p>
            <label htmlFor="staff-recovery-codes">Резервные коды</label>
            <textarea id="staff-recovery-codes" readOnly rows={10} value={recoveryCodes.join("\n")} autoComplete="off" spellCheck={false} />
            <label><input type="checkbox" checked={recoverySaved} onChange={(event) => setRecoverySaved(event.target.checked)} /> Я сохранил коды вне Букера</label>
            <button type="button" disabled={!recoverySaved} onClick={leaveEnrollment}>Перейти ко входу</button>
          </section>
        )
      ) : (
      <form className="card surface-glass" style={{ display: "grid", gap: 12, maxWidth: 420 }} onSubmit={onSubmit}>
        {mode === "register" ? (
          <>
            <label>
              Имя
              <input name="full_name" required />
            </label>
            <fieldset className="role-picker" data-testid="role-picker">
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
                  data-testid={`role-option-${value}`}
                  onClick={() => setSelectedRole(value)}
                >
                  <span><strong>{title}</strong><small>{description}</small></span>
                  <span aria-hidden>{selectedRole === value ? "✓" : ""}</span>
                </button>
              ))}
            </fieldset>
          </>
        ) : null}
        {mode !== "reset" ? (
          <label>
            Email
            <input name="email" type="email" autoComplete="username" required />
          </label>
        ) : null}
        {mode !== "recover" ? (
          <label>
            {mode === "reset" ? "Новый пароль" : "Пароль"}
            <input
              name="password"
              type="password"
              autoComplete={mode === "register" || mode === "reset" ? "new-password" : "current-password"}
              required
              minLength={8}
            />
          </label>
        ) : null}
        {mode === "login" ? (
          <div style={{ display: "grid", gap: 4 }}>
            <label htmlFor="login-totp">Код из приложения-аутентификатора</label>
            <input
              id="login-totp"
              name="totp"
              type="text"
              inputMode="numeric"
              autoComplete="one-time-code"
              pattern="[0-9]{6}"
              minLength={6}
              maxLength={6}
              aria-describedby="login-totp-help"
            />
            <small id="login-totp-help">Шесть цифр. Заполните, если у вас включён второй фактор.</small>
          </div>
        ) : null}
        {mode === "reset" ? (
          <div style={{ display: "grid", gap: 4 }}>
            <label htmlFor="reset-totp">Код из приложения-аутентификатора</label>
            <input id="reset-totp" name="totp" inputMode="numeric" autoComplete="one-time-code" pattern="[0-9]{6}" minLength={6} maxLength={6} aria-describedby="reset-totp-help" />
            <small id="reset-totp-help">Шесть цифр. Требуется при сбросе пароля администратора.</small>
          </div>
        ) : null}
        {mode === "register" ? (
          <Fragment key={legalConsentKey}>
            {legalState.required_documents.length ? <ul>
              {legalState.required_documents.map((document) => <li key={document.key}>
                <a href={legalDocumentHref(document.key)}>{legalDocumentLabel(document.key)}</a> · редакция {document.version} · {document.status === "draft" ? "черновик" : "опубликован"}
              </li>)}
            </ul> : null}
            <div className="unknown">
              <input id="accept_offer" name="accept_offer" type="checkbox" required />
              <span>
                <label htmlFor="accept_offer" className="inline-label">
                  {legalState.draftTest ? "Ознакомлен(а) с черновиком" : "Принимаю"}
                </label>{" "}
                <a href="/legal/offer">{legalState.draftTest ? "оферты" : "оферту"}</a> и правила использования сервиса.
              </span>
            </div>
            <div className="unknown">
              <input id="accept_privacy" name="accept_privacy" type="checkbox" required />
              <span>
                <label htmlFor="accept_privacy" className="inline-label">
                  {legalState.draftTest ? "Ознакомлен(а)" : "Согласен(на)"}
                </label>{" "}
                с <a href="/legal/privacy">политикой обработки персональных данных</a>.
              </span>
            </div>
            <div className="unknown">
              <input id="accept_consent_texts" name="accept_consent_texts" type="checkbox" required />
              <span>
                <label htmlFor="accept_consent_texts" className="inline-label">
                  {legalState.draftTest ? "Ознакомлен(а) с черновиком" : "Согласен(на) с"}
                </label>{" "}
                <a href="/legal/consent-texts">{legalState.draftTest ? "текстов согласий" : "текстами согласий"}</a>.
              </span>
            </div>
            {legalState.draftTest ? <div className="unknown">
              <input id="draft_test_acknowledgement" name="draft_test_acknowledgement" type="checkbox" required />
              <label htmlFor="draft_test_acknowledgement" className="inline-label">
                Понимаю, что пакет черновой, регистрация тестовая и эти отметки не заменяют юридический акцепт.
              </label>
            </div> : null}
            <label className="unknown">
              <input name="marketing_opt_in" type="checkbox" />
              Получать новости продукта и специальные предложения. Необязательно.
            </label>
          </Fragment>
        ) : null}
        {error ? <p role="alert" style={{ color: "var(--danger)" }}>{error}</p> : null}
        {notice ? <p className="timeline">{notice}</p> : null}
        <button type="submit" disabled={pending || (mode === "register" && legalUnavailable)}>
          {pending
            ? "Обрабатываем…"
            : mode === "reset"
              ? "Сохранить пароль"
              : mode === "recover"
                ? "Отправить инструкцию"
                : mode === "login"
                  ? "Войти"
                  : "Создать аккаунт"}
        </button>
      </form>
      )}
      <p style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
        {mode === "staff-recovery-codes" ? null : mode === "staff-recover" ? (
          <button type="button" className="secondary" onClick={() => { setEnrollSecret(""); setMode("login"); setError(""); }}>Вернуться ко входу</button>
        ) : mode === "verify" || mode === "workspace" ? (
          <button type="button" className="secondary" onClick={() => { setVerificationToken(""); setMode("login"); setError(""); setNotice(""); }}>Вернуться ко входу</button>
        ) : mode === "enroll" && enrollStep === "recovery" ? null : mode === "enroll" ? (
          <button type="button" className="secondary" onClick={leaveEnrollment}>Вернуться ко входу</button>
        ) : mode === "reset" ? (
          <button type="button" className="secondary" onClick={() => setMode("login")}>
            Вернуться ко входу
          </button>
        ) : (
          <>
            <button type="button" className="secondary" onClick={() => setMode(mode === "login" ? "register" : "login")}
              disabled={mode === "login" && legalUnavailable}>
              {mode === "login" ? "Создать аккаунт" : "Вернуться ко входу"}
            </button>
            {mode === "login" ? (
              <>
                <button type="button" className="secondary" onClick={() => setMode("recover")}>Забыли пароль?</button>
                <button type="button" className="secondary" onClick={() => { setEnrollSecret(generateTotpSecret()); setError(""); setNotice(""); setMode("staff-recover"); }}>Потеряли Authenticator?</button>
                <button type="button" className="secondary" onClick={() => { setOperatorEnrollment(new URLSearchParams(window.location.search).get("next") === "/operator"); setToken(null); localStorage.removeItem("booker.admin"); setError(""); setNotice(""); setMode("enroll"); }}>
                  {operatorEnrollment ? "Настроить второй фактор оператора" : "Настроить второй фактор администратора"}
                </button>
              </>
            ) : null}
          </>
        )}
      </p>
    </main>
  );
}
