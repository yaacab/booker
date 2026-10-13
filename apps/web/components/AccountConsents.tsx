"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";
import { api, ApiError, getToken } from "@/lib/api";
import { consentActionLabel, consentKindLabel, consentReacceptState, createConsentSessionGuard, type ConsentHistory, type ConsentSession } from "@/lib/consents";
import { getPublicLegalPack, legalDocumentHref, legalDocumentLabel, type LegalPack } from "@/lib/legalPack";

const PAGE_SIZE = 20;
const EMPTY_CHECKS = { offer: false, privacy: false, consent_texts: false };

function errorText(error: unknown): string {
  return error instanceof Error ? error.message : "Не удалось выполнить действие";
}

export default function AccountConsents() {
  const [history, setHistory] = useState<ConsentHistory | null>(null);
  const [pack, setPack] = useState<LegalPack | null>(null);
  const [checks, setChecks] = useState(EMPTY_CHECKS);
  const [shown, setShown] = useState(PAGE_SIZE);
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");
  const [notice, setNotice] = useState("");
  const guard = useRef(createConsentSessionGuard(getToken));
  const mounted = useRef(false);

  function clearPrivate() {
    setHistory(null);
    setPack(null);
    setChecks(EMPTY_CHECKS);
    setShown(PAGE_SIZE);
    setBusy(false);
    setError("");
    setNotice("");
  }

  function current(session: ConsentSession): boolean {
    if (!mounted.current) return false;
    if (guard.current.isCurrent(session)) return true;
    checkSession();
    return false;
  }

  async function refresh(session = guard.current.capture()): Promise<boolean> {
    if (!current(session) || !session.token) return false;
    const [nextHistory, nextPack] = await Promise.all([
      api<ConsentHistory>("/me/consents", { cache: "no-store" }),
      getPublicLegalPack(),
    ]);
    if (!current(session)) return false;
    setHistory(nextHistory);
    setPack(nextPack);
    return true;
  }

  function load(session: ConsentSession) {
    setLoading(true);
    void refresh(session).catch((cause: unknown) => {
      if (!current(session)) return;
      setHistory(null);
      setPack(null);
      setError(errorText(cause));
    }).finally(() => {
      if (current(session)) setLoading(false);
    });
  }

  function checkSession(force = false) {
    const changed = guard.current.sync();
    if (!changed && !force) return;
    if (force) guard.current.invalidate();
    clearPrivate();
    const session = guard.current.capture();
    if (session.token) load(session);
    else setLoading(false);
  }

  function onStorage(event: StorageEvent) {
    if (event.key === "booker.token" && event.oldValue !== event.newValue) checkSession(true);
    else checkSession();
  }

  function onFocus() { checkSession(); }

  useEffect(() => {
    mounted.current = true;
    guard.current.sync();
    const session = guard.current.capture();
    if (session.token) load(session);
    else setLoading(false);
    window.addEventListener("storage", onStorage);
    window.addEventListener("focus", onFocus);
    return () => {
      mounted.current = false;
      guard.current.invalidate();
      window.removeEventListener("storage", onStorage);
      window.removeEventListener("focus", onFocus);
    };
  }, []);

  const reaccept = consentReacceptState(pack, history);
  const required = pack?.documents.filter((document) => reaccept.accepted_documents.some((accepted) => accepted.key === document.key)) || [];
  const allChecked = required.length === 3 && required.every((document) => checks[document.key as keyof typeof EMPTY_CHECKS]);
  const entries = [...(history?.history || [])].reverse();

  async function withdrawMarketing() {
    if ((!history?.marketing_email_active && !history?.marketing_test_selected) || busy) return;
    const session = guard.current.capture();
    if (!current(session)) return;
    setBusy(true);
    setError("");
    setNotice("");
    try {
      const result = await api<{ marketing_email_active: boolean; marketing_test_selected: boolean }>("/me/consents/marketing/withdraw", { method: "POST" });
      if (!current(session)) return;
      setHistory((current) => current ? { ...current, marketing_email_active: result.marketing_email_active,
        marketing_test_selected: result.marketing_test_selected } : current);
      setNotice(history.marketing_test_selected ? "Тестовая отметка о рассылке отозвана." : "Согласие на рассылку отозвано.");
      try { await refresh(session); if (!current(session)) return; } catch (cause) {
        if (!current(session)) return;
        if (cause instanceof ApiError && [401, 403].includes(cause.status)) setHistory(null);
        setError("Историю не удалось обновить. " + errorText(cause));
      }
    } catch (cause) {
      if (!current(session)) return;
      if (cause instanceof ApiError && [401, 403].includes(cause.status)) setHistory(null);
      setError(errorText(cause));
    } finally {
      if (current(session)) setBusy(false);
    }
  }

  async function acceptCurrent() {
    if (!reaccept.available || !allChecked || busy) return;
    const session = guard.current.capture();
    if (!current(session)) return;
    setBusy(true);
    setError("");
    setNotice("");
    try {
      const latest = await getPublicLegalPack();
      if (!current(session)) return;
      const latestState = consentReacceptState(latest, history);
      if (!latestState.available || JSON.stringify(latestState.accepted_documents) !== JSON.stringify(reaccept.accepted_documents)) {
        setPack(latest);
        setChecks(EMPTY_CHECKS);
        setError("Редакция документов изменилась или недоступна. Проверьте её перед повторным действием.");
        return;
      }
      await api("/me/consents/reaccept", {
        method: "POST",
        body: JSON.stringify({
          accepted_documents: reaccept.accepted_documents,
          accept_offer: checks.offer,
          accept_privacy: checks.privacy,
          accept_processing: checks.consent_texts,
        }),
      });
      if (!current(session)) return;
      setChecks(EMPTY_CHECKS);
      setNotice("Повторное принятие опубликованной редакции зарегистрировано.");
      try { await refresh(session); if (!current(session)) return; } catch (cause) {
        if (!current(session)) return;
        if (cause instanceof ApiError && [401, 403].includes(cause.status)) setHistory(null);
        setError("Историю не удалось обновить. " + errorText(cause));
      }
    } catch (cause) {
      if (!current(session)) return;
      if (cause instanceof ApiError && [401, 403].includes(cause.status)) setHistory(null);
      if (cause instanceof ApiError && cause.status === 409) {
        setChecks(EMPTY_CHECKS);
        try { await refresh(session); } catch { if (current(session)) setHistory(null); }
        if (!current(session)) return;
        setError("Состояние согласий изменилось. Данные обновлены; проверьте их снова.");
      } else setError(errorText(cause));
    } finally {
      if (current(session)) setBusy(false);
    }
  }

  return (
    <section className="card surface-glass" aria-labelledby="account-consents-title" style={{ marginTop: 16 }}>
      <h2 id="account-consents-title">Согласия и документы</h2>
      {loading ? <p>Загружаем историю согласий…</p> : null}
      {error ? <p role="alert">{error}</p> : null}
      {notice ? <p role="status">{notice}</p> : null}
      {history ? (
        <>
          <p>Рассылка: {history.marketing_email_active ? "согласие действует" : history.marketing_test_selected
            ? "есть тестовая отметка; действующего согласия нет" : "согласие не действует"}.</p>
          {history.marketing_email_active || history.marketing_test_selected ? (
            <button type="button" className="secondary" disabled={busy} onClick={() => void withdrawMarketing()}>
              {history.marketing_test_selected ? "Отозвать тестовую отметку о рассылке" : "Отозвать согласие на рассылку"}
            </button>
          ) : null}
          <h3>История</h3>
          {history.legacy_evidence_status === "legacy_unknown" ? (
            <p>Для прежней регистрации есть историческая запись, но версия принятых документов не подтверждена. Эта запись не считается новым принятием.</p>
          ) : null}
          {entries.length ? (
            <>
              <ul>
                {entries.slice(0, shown).map((event) => (
                  <li key={event.id}>
                    {consentKindLabel(event.kind)} · {consentActionLabel(event.action)} · {event.document_version || "без версии"} · {new Date(event.created_at).toLocaleString("ru-RU")}
                  </li>
                ))}
              </ul>
              {entries.length > shown ? (
                <button type="button" className="secondary" onClick={() => setShown((count) => count + PAGE_SIZE)}>Показать ещё</button>
              ) : null}
            </>
          ) : <p>Записей пока нет.</p>}
          {pack?.status === "draft" ? (
            <p>Текущий пакет документов — черновик. Повторное юридическое принятие недоступно; доступ к аккаунту сохраняется.</p>
          ) : null}
          {pack?.status === "unavailable" || !pack ? <p>Текущий пакет документов недоступен. Доступ к аккаунту сохраняется.</p> : null}
          {reaccept.available ? (
            <div>
              <h3>Новая опубликованная редакция</h3>
              <p>Ознакомьтесь с каждым документом и отметьте его отдельно.</p>
              {required.map((document) => (
                <label key={document.key} style={{ display: "block", marginBottom: 8 }}>
                  <input type="checkbox" checked={checks[document.key as keyof typeof EMPTY_CHECKS]}
                    onChange={(event) => setChecks((current) => ({ ...current, [document.key]: event.target.checked }))} />{" "}
                  Принимаю <Link href={legalDocumentHref(document.key)} target="_blank" rel="noopener noreferrer">{legalDocumentLabel(document.key)}</Link> · редакция {document.version}
                </label>
              ))}
              <button type="button" disabled={!allChecked || busy} onClick={() => void acceptCurrent()}>
                {busy ? "Сохраняем…" : "Принять текущую редакцию"}
              </button>
            </div>
          ) : null}
        </>
      ) : null}
    </section>
  );
}
