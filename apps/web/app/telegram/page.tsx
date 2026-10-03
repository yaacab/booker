"use client";

import { FormEvent, useRef, useState } from "react";
import Script from "next/script";
import { useRouter } from "next/navigation";
import { BrandLockup } from "@/components/BrandLockup";
import { api, ApiError, createOrgWithConfirm, setActiveOrg, setToken } from "@/lib/api";
import { cabinetPathForKind } from "@/lib/cabinetRoutes";
import { getPublicLegalPack, legalDocumentHref, legalDocumentLabel, registrationLegalState, type LegalPack } from "@/lib/legalPack";
import { safeNext } from "@/lib/next";

type TelegramWebApp = { initData: string; ready?: () => void; expand?: () => void };
type TelegramWindow = Window & { Telegram?: { WebApp?: TelegramWebApp } };
type Flow = "loading" | "outside" | "legal" | "totp" | "workspace" | "error";
type CompleteResult = {
  token: string;
  user_id: string;
  is_platform_admin: boolean;
  is_support_operator: boolean;
  onboarding_required: boolean;
};

function telegramWebApp(): TelegramWebApp | null {
  return (window as TelegramWindow).Telegram?.WebApp ?? null;
}

export default function TelegramPage() {
  const router = useRouter();
  const started = useRef(false);
  const [flow, setFlow] = useState<Flow>("loading");
  const [pendingToken, setPendingToken] = useState<string | null>(null);
  const [legalPack, setLegalPack] = useState<LegalPack | null>(null);
  const [error, setError] = useState("");
  const [pending, setPending] = useState(false);
  const [selectedRole, setSelectedRole] = useState("customer");

  const legalState = registrationLegalState(legalPack);
  const legalConsentKey = legalState.accepted_documents.map((item) =>
    `${item.key}:${item.version}:${item.content_hash}`).join("|");

  async function loadLegal() {
    const pack = await getPublicLegalPack();
    setLegalPack(pack);
    if (!registrationLegalState(pack).available) {
      throw new Error("Регистрация через Telegram сейчас недоступна: сервер не подтвердил юридический пакет.");
    }
  }

  async function enterBooker(result: CompleteResult) {
    setToken(result.token);
    if (result.is_platform_admin) localStorage.setItem("booker.admin", "1");
    else localStorage.removeItem("booker.admin");
    if (result.is_support_operator) {
      router.replace("/operator");
      return;
    }
    if (result.is_platform_admin) {
      router.replace("/admin");
      return;
    }
    if (result.onboarding_required) {
      setFlow("workspace");
      return;
    }
    const me = await api<{
      organizations?: { id: string; kind: string }[];
      active_organization_id?: string | null;
    }>("/me");
    const org = me.organizations?.find((item) => item.id === me.active_organization_id)
      ?? me.organizations?.[0];
    if (!org) {
      setFlow("workspace");
      return;
    }
    setActiveOrg(org.id);
    const rawNext = new URLSearchParams(window.location.search).get("next");
    const next = safeNext(rawNext, cabinetPathForKind(org.kind));
    router.replace(!rawNext || next === "/cabinet" ? cabinetPathForKind(org.kind) : next);
  }

  async function complete(token: string, extra: Record<string, unknown> = {}) {
    try {
      const result = await api<CompleteResult>("/auth/telegram/complete", {
        method: "POST", body: JSON.stringify({ pending_token: token, ...extra }),
      });
      setPendingToken(null);
      await enterBooker(result);
    } catch (err) {
      if (err instanceof ApiError && err.status === 422 && !extra.accept_offer) {
        try {
          await loadLegal();
          setFlow("legal");
          return;
        } catch (legalError) {
          setError(legalError instanceof Error ? legalError.message : "Регистрация временно недоступна.");
          setFlow("error");
          return;
        }
      }
      if (err instanceof ApiError && err.status === 401 &&
          err.message === "Нужен код второго фактора") {
        setError("Введите шестизначный код из приложения-аутентификатора Букера.");
        setFlow("totp");
        return;
      }
      setError(err instanceof Error ? err.message : "Не удалось войти через Telegram.");
      setFlow("error");
    }
  }

  async function startTelegram() {
    if (started.current) return;
    started.current = true;
    const telegram = telegramWebApp();
    if (!telegram?.initData) {
      setFlow("outside");
      return;
    }
    telegram.ready?.();
    telegram.expand?.();
    setPending(true);
    try {
      const prepared = await api<{ pending_token: string }>("/auth/telegram/prepare", {
        method: "POST", body: JSON.stringify({ init_data: telegram.initData }),
      });
      setPendingToken(prepared.pending_token);
      // A previous browser session may belong to another Booker account.
      // The server-verified Telegram subject determines the new session.
      setToken(null);
      localStorage.removeItem("booker.admin");
      await complete(prepared.pending_token);
    } catch (err) {
      setError(err instanceof Error ? err.message : "Не удалось проверить Telegram.");
      setFlow("error");
    } finally {
      setPending(false);
    }
  }

  async function submitLegal(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!pendingToken || pending || !legalState.available) return;
    setPending(true);
    setError("");
    const form = new FormData(event.currentTarget);
    try {
      const freshPack = await getPublicLegalPack();
      const freshState = registrationLegalState(freshPack);
      if (!freshState.available || freshPack?.pack_version !== legalPack?.pack_version ||
          freshPack?.acceptance_effect !== legalPack?.acceptance_effect ||
          JSON.stringify(freshState.accepted_documents) !== JSON.stringify(legalState.accepted_documents)) {
        setLegalPack(freshPack);
        throw new Error("Редакция документов изменилась. Ознакомьтесь с ней и подтвердите отметки заново.");
      }
      await complete(pendingToken, {
        accept_offer: form.get("accept_offer") === "on",
        accept_privacy: form.get("accept_privacy") === "on",
        accept_processing: form.get("accept_processing") === "on",
        accepted_documents: legalState.accepted_documents,
        draft_test_acknowledgement: legalState.draftTest && form.get("draft_test_acknowledgement") === "on",
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Не удалось подтвердить документы.");
    } finally {
      setPending(false);
    }
  }

  async function submitTotp(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!pendingToken || pending) return;
    setPending(true);
    setError("");
    try {
      const form = new FormData(event.currentTarget);
      await complete(pendingToken, { totp: String(form.get("totp") || "").trim() });
    } finally {
      setPending(false);
    }
  }

  async function createWorkspace(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (pending) return;
    setPending(true);
    setError("");
    const form = new FormData(event.currentTarget);
    try {
      const kind = String(form.get("kind") || "customer");
      const org = await createOrgWithConfirm({
        name: String(form.get("name") || "").trim(), kind, city: "Москва",
      });
      setActiveOrg(org.id);
      router.replace(cabinetPathForKind(kind));
    } catch (err) {
      setError(err instanceof Error ? err.message : "Не удалось создать рабочее пространство.");
    } finally {
      setPending(false);
    }
  }

  return (
    <main className="workspace" style={{ maxWidth: 560, margin: "0 auto", paddingBlock: 32 }}>
      <Script
        src="https://telegram.org/js/telegram-web-app.js?63"
        strategy="afterInteractive"
        onReady={() => { void startTelegram(); }}
        onError={() => { setError("Не удалось загрузить Telegram Mini App."); setFlow("error"); }}
      />
      <BrandLockup />
      <h1>Букер в Telegram</h1>
      {flow === "loading" ? <p role="status">Проверяем вход через Telegram…</p> : null}
      {flow === "outside" ? <section className="card surface-glass" aria-label="Вход через Telegram">
        <p>Откройте Букер из Telegram Mini App, чтобы войти этим способом.</p>
        <a href="/login">Войти по email</a>
      </section> : null}
      {flow === "totp" ? <form className="card surface-glass" onSubmit={submitTotp} style={{ display: "grid", gap: 12 }}>
        <p>Для оператора и администратора нужен второй фактор Букера.</p>
        <label>Код Authenticator
          <input name="totp" inputMode="numeric" autoComplete="one-time-code" pattern="[0-9]{6}" minLength={6} maxLength={6} required />
        </label>
        {error ? <p role="alert">{error}</p> : null}
        <button type="submit" disabled={pending}>{pending ? "Проверяем…" : "Подтвердить вход"}</button>
      </form> : null}
      {flow === "legal" ? <form key={legalConsentKey} className="card surface-glass" onSubmit={submitLegal} style={{ display: "grid", gap: 12 }}>
        <h2>Первый вход в Букер</h2>
        <p>Telegram подтвердил ваш аккаунт. Ознакомьтесь с документами Букера перед созданием кабинета.</p>
        <ul>{legalState.required_documents.map((document) => <li key={document.key}>
          <a href={legalDocumentHref(document.key)}>{legalDocumentLabel(document.key)}</a> · редакция {document.version} · {document.status === "draft" ? "черновик" : "опубликован"}
        </li>)}</ul>
        <label><input name="accept_offer" type="checkbox" required /> {legalState.draftTest ? "Ознакомлен(а) с черновиком оферты" : "Принимаю оферту"}</label>
        <label><input name="accept_privacy" type="checkbox" required /> {legalState.draftTest ? "Ознакомлен(а) с политикой" : "Согласен(на) с политикой обработки данных"}</label>
        <label><input name="accept_processing" type="checkbox" required /> {legalState.draftTest ? "Ознакомлен(а) с черновиком согласий" : "Согласен(на) на обработку данных"}</label>
        {legalState.draftTest ? <label><input name="draft_test_acknowledgement" type="checkbox" required /> Понимаю, что документы черновые и регистрация тестовая.</label> : null}
        {error ? <p role="alert">{error}</p> : null}
        <button type="submit" disabled={pending || !legalState.available}>{pending ? "Подтверждаем…" : "Продолжить"}</button>
      </form> : null}
      {flow === "workspace" ? <form className="card surface-glass" onSubmit={createWorkspace} style={{ display: "grid", gap: 12 }}>
        <h2>Создайте рабочее пространство</h2>
        <label>Название пространства<input name="name" minLength={2} required /></label>
        <label>Кто вы?
          <select name="kind" value={selectedRole} onChange={(event) => setSelectedRole(event.target.value)}>
            <option value="customer">Заказчик</option>
            <option value="artist">Исполнитель</option>
            <option value="venue">Площадка</option>
          </select>
        </label>
        {error ? <p role="alert">{error}</p> : null}
        <button type="submit" disabled={pending}>{pending ? "Создаём…" : "Создать пространство"}</button>
      </form> : null}
      {flow === "error" ? <section className="card surface-glass" aria-label="Ошибка входа">
        <p role="alert">{error || "Не удалось войти через Telegram."}</p>
        <p>Закройте и снова откройте Mini App из Telegram. Если ошибка повторится, обратитесь в поддержку.</p>
        <a href="/support">Поддержка Букера</a>
      </section> : null}
    </main>
  );
}
