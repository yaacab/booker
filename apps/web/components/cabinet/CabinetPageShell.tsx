"use client";

import Link from "next/link";
import type { ReactNode } from "react";
import { setToken } from "@/lib/api";
import { CabinetMode, cabinetHeadline, cabinetTitle } from "@/lib/cabinetRoutes";
import { KIND_LABEL } from "@/lib/copy";
import { loginHref } from "@/lib/next";

type CabinetPageShellProps = {
  mode: CabinetMode;
  kindKey?: string;
  ready: boolean;
  error: string;
  email: string;
  orgName: string;
  empty: boolean;
  emptyState: ReactNode;
  children: ReactNode;
  footer?: ReactNode;
};

function kindLabelForMode(mode: CabinetMode, kindKey?: string): string {
  if (kindKey && KIND_LABEL[kindKey]) return KIND_LABEL[kindKey];
  if (mode === "performer") return KIND_LABEL.artist || "Букер";
  return KIND_LABEL[mode] || "Букер";
}

export function CabinetPageShell({
  mode,
  kindKey,
  ready,
  error,
  email,
  orgName,
  empty,
  emptyState,
  children,
  footer,
}: CabinetPageShellProps) {
  const cabinetPath = `/cabinet/${mode}`;
  const showWidgets = ready && !error && !empty;

  return (
    <main className={`${mode}-cabinet`} aria-labelledby="cabinet-heading">
      {showWidgets ? (
        <a className="skip" href="#cabinet-widgets">
          К виджетам кабинета
        </a>
      ) : null}
      <p className="kicker">
        {cabinetTitle(mode)} · {kindLabelForMode(mode, kindKey)}
      </p>
      <h1 id="cabinet-heading">{cabinetHeadline(mode)}</h1>
      {email ? (
        <p className="timeline">
          {email}
          {orgName ? ` · ${orgName}` : ""}
        </p>
      ) : null}
      {!ready ? (
        <div
          className="skeleton cabinet-skeleton"
          role="status"
          aria-busy="true"
          aria-label="Загрузка кабинета"
        />
      ) : null}
      {error ? (
        <p role="alert">
          {error}. <Link href={loginHref(cabinetPath)}>Войти</Link>
        </p>
      ) : null}
      {ready && !error && empty ? emptyState : null}
      {showWidgets ? (
        <div
          id="cabinet-widgets"
          className="dashboard-grid"
          role="region"
          aria-label="Виджеты кабинета"
        >
          {children}
        </div>
      ) : null}
      {footer}
      <p style={{ marginTop: 24 }}>
        <button
          type="button"
          className="secondary"
          aria-label="Выйти из аккаунта"
          onClick={() => {
            setToken(null);
            localStorage.removeItem("booker.admin");
            window.location.href = "/login";
          }}
        >
          Выйти
        </button>
      </p>
    </main>
  );
}
