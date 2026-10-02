"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import AdminSupportQueue from "@/components/AdminSupportQueue";
import { api, ApiError, getToken, SESSION_CHANGED_EVENT } from "@/lib/api";
import { loginHref } from "@/lib/next";

type Operator = { id: string; is_support_operator?: boolean; totp_enabled?: boolean };
type Access = { status: "loading" | "login" | "forbidden" | "enroll" | "ready"; operatorId?: string; token?: string };

export default function OperatorPage() {
  const [access, setAccess] = useState<Access>({ status: "loading" });

  useEffect(() => {
    let requestId = 0;
    const checkAccess = () => {
      const id = ++requestId;
      const token = getToken();
      if (!token) {
        setAccess({ status: "login" });
        return;
      }
      setAccess({ status: "loading" });
      void api<Operator>("/me", { cache: "no-store" }).then((me) => {
        if (id !== requestId || getToken() !== token) return;
        if (!me.is_support_operator || !me.id) setAccess({ status: "forbidden" });
        else if (!me.totp_enabled) setAccess({ status: "enroll" });
        else setAccess({ status: "ready", operatorId: me.id, token });
      }).catch((error: unknown) => {
        if (id !== requestId || getToken() !== token) return;
        setAccess({ status: error instanceof ApiError && error.status === 401 ? "login" : "forbidden" });
      });
    };
    const onStorage = (event: StorageEvent) => {
      if (event.key === "booker.token" || event.key === null) checkAccess();
    };
    const onVisible = () => {
      if (document.visibilityState === "visible") checkAccess();
    };
    checkAccess();
    window.addEventListener(SESSION_CHANGED_EVENT, checkAccess);
    window.addEventListener("storage", onStorage);
    window.addEventListener("pageshow", checkAccess);
    document.addEventListener("visibilitychange", onVisible);
    return () => {
      ++requestId;
      window.removeEventListener(SESSION_CHANGED_EVENT, checkAccess);
      window.removeEventListener("storage", onStorage);
      window.removeEventListener("pageshow", checkAccess);
      document.removeEventListener("visibilitychange", onVisible);
    };
  }, []);

  return (
    <main>
      <p className="kicker">Поддержка Букера</p>
      <h1>Кабинет оператора</h1>
      {access.status === "loading" ? <p role="status">Проверяем доступ…</p> : null}
      {access.status === "login" ? <p>Для работы с обращениями нужен вход. <Link href={loginHref("/operator")}>Войти</Link></p> : null}
      {access.status === "forbidden" ? <p role="alert">Нет доступа к кабинету оператора.</p> : null}
      {access.status === "enroll" ? <p>Для работы с обращениями настройте второй фактор. <Link href="/login?next=%2Foperator&enroll=1">Перейти к настройке</Link></p> : null}
      {access.status === "ready" && access.operatorId && access.token && getToken() === access.token ? (
        <article className="card surface-glass" style={{ minWidth: 0 }}>
          <AdminSupportQueue key={access.token} operatorId={access.operatorId} />
        </article>
      ) : null}
    </main>
  );
}
