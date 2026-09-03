"use client";

import Link from "next/link";
import type { ReactNode } from "react";
import { setToken } from "@/lib/api";
import { CabinetMode, cabinetHeadline, cabinetTitle } from "@/lib/cabinetRoutes";
import { KIND_LABEL } from "@/lib/copy";
import { loginHref } from "@/lib/next";

export type CabinetMetric = {
  label: string;
  value: string | number;
  hint?: string;
  tone?: "default" | "ok" | "wait" | "live" | "bad";
};

export type CabinetAction = {
  href: string;
  label: string;
  primary?: boolean;
};

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
  subtitle?: string;
  metrics?: CabinetMetric[];
  actions?: CabinetAction[];
  lead?: ReactNode;
};

function kindLabelForMode(mode: CabinetMode, kindKey?: string): string {
  if (kindKey && KIND_LABEL[kindKey]) return KIND_LABEL[kindKey];
  if (mode === "performer") return KIND_LABEL.artist || "Исполнитель";
  return KIND_LABEL[mode] || "Букер";
}

function roleBlurb(mode: CabinetMode): string {
  if (mode === "venue") {
    return "Управляйте залами и свободными датами. Заказчик находит вас в каталоге — вы отвечаете на заявки.";
  }
  if (mode === "performer") {
    return "Держите календарь открытым и отвечайте на запросы. Вы не собираете события — вас бронируют.";
  }
  return "Соберите состав на дату, сравните предложения и подтвердите условия в Deal Room.";
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
  subtitle,
  metrics,
  actions,
  lead,
}: CabinetPageShellProps) {
  const cabinetPath = `/cabinet/${mode}`;
  const showWidgets = ready && !error && !empty;
  const roleLabel = kindLabelForMode(mode, kindKey);

  return (
    <main className={`cabinet-v2 cabinet-${mode}`} data-cabinet={mode} aria-labelledby="cabinet-heading">
      {showWidgets ? (
        <a className="skip" href="#cabinet-widgets">
          К виджетам кабинета
        </a>
      ) : null}

      <header className="cabinet-hero">
        <div className="cabinet-hero-copy">
          <p className="cabinet-eyebrow">
            <span className="cabinet-role-pill">{cabinetTitle(mode)}</span>
            <span className="cabinet-role-sep" aria-hidden>
              ·
            </span>
            <span>{roleLabel}</span>
          </p>
          <h1 id="cabinet-heading">{cabinetHeadline(mode)}</h1>
          <p className="cabinet-lede">{subtitle || roleBlurb(mode)}</p>
          {email ? (
            <p className="cabinet-identity">
              <span className="cabinet-identity-mail">{email}</span>
              {orgName ? <span className="cabinet-identity-org">{orgName}</span> : null}
            </p>
          ) : null}
        </div>
        {actions && actions.length > 0 ? (
          <div className="cabinet-hero-actions">
            {actions.map((a) => (
              <Link
                key={a.href + a.label}
                className={a.primary ? "btn" : "btn secondary"}
                href={a.href}
              >
                {a.label}
              </Link>
            ))}
          </div>
        ) : null}
      </header>

      {ready && metrics && metrics.length > 0 ? (
        <section className="cabinet-metrics" aria-label="Сводка кабинета">
          {metrics.map((m) => (
            <article key={m.label} className={`cabinet-metric tone-${m.tone || "default"}`}>
              <p className="cabinet-metric-value">{m.value}</p>
              <p className="cabinet-metric-label">{m.label}</p>
              {m.hint ? <p className="cabinet-metric-hint">{m.hint}</p> : null}
            </article>
          ))}
        </section>
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
        <p className="cabinet-alert" role="alert">
          {error}. <Link href={loginHref(cabinetPath)}>Войти</Link>
        </p>
      ) : null}

      {lead && ready && !error ? <div className="cabinet-lead">{lead}</div> : null}

      {ready && !error && empty ? <div className="cabinet-empty">{emptyState}</div> : null}

      {showWidgets ? (
        <div id="cabinet-widgets" className="cabinet-board" role="region" aria-label="Виджеты кабинета">
          {children}
        </div>
      ) : null}

      {footer && ready && !error ? <div className="cabinet-footer-block">{footer}</div> : null}

      <p className="cabinet-signout">
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
