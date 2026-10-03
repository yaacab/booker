"use client";

import { useEffect, useState } from "react";
import { BrandLockup } from "@/components/BrandLockup";
import { apiBase } from "@/lib/api";

type Result = "checking" | "verified" | "error";

export default function VerifyEmailPage() {
  const [result, setResult] = useState<Result>("checking");

  useEffect(() => {
    const token = new URLSearchParams(window.location.hash.slice(1)).get("verify");
    window.history.replaceState(null, "", window.location.pathname);
    if (!token || token.length < 32 || token.length > 128) {
      setResult("error");
      return;
    }
    void fetch(`${apiBase()}/auth/email-verification/external-confirm`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ token }),
    }).then((response) => {
      setResult(response.ok ? "verified" : "error");
    }).catch(() => { setResult("error"); });
  }, []);

  return <main className="workspace" style={{ maxWidth: 560, margin: "0 auto", paddingBlock: 32 }}>
    <BrandLockup />
    <h1>Подтверждение email</h1>
    {result === "checking" ? <p role="status">Проверяем ссылку…</p> : null}
    {result === "verified" ? <section className="card surface-glass">
      <p role="status">Адрес подтверждён. Вернитесь в Telegram Mini App и нажмите «Я подтвердил(а) адрес».</p>
    </section> : null}
    {result === "error" ? <section className="card surface-glass">
      <p role="alert">Ссылка недействительна или срок её действия истёк.</p>
      <p>Откройте Букер из Telegram и запросите письмо повторно.</p>
    </section> : null}
  </main>;
}
