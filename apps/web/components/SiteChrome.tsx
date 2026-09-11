"use client";

import Link from "next/link";
import { DemoBanner } from "./DemoBanner";
import { EditionToggle } from "./EditionToggle";
import { useEffect, useRef, useState } from "react";
import { usePathname } from "next/navigation";
import { BrandLockup } from "@/components/BrandLockup";
import { WorkspaceNavigation } from "@/components/WorkspaceNavigation";
import { WorkspaceSwitcher } from "@/components/WorkspaceSwitcher";
import { api, getActiveOrg, getToken, setToken, trackClientEvent } from "@/lib/api";
import { orgKindToCabinetMode, supplyCalendarHref, supplyRequestsHref, type CabinetMode } from "@/lib/cabinetRoutes";
import { loginHref } from "@/lib/next";
import { isEventStudioMapV1 } from "@/lib/features";

const ADMIN_KEY = "booker.admin";
const DEFAULT_TITLE = "Букер — сделки с артистами и площадками";

function tabTitle(path: string): string {
  if (path === "/") return DEFAULT_TITLE;
  if (path.startsWith("/search")) return "Каталог · Букер";
  if (path.startsWith("/events/new")) return "Новая заявка · Букер";
  if (path.startsWith("/events/")) return "Событие · Букер";
  if (path.startsWith("/cabinet")) return "Сделки · Букер";
  if (path.startsWith("/profile")) return "Профиль · Букер";
  if (path.startsWith("/admin")) return "Пульт · Букер";
  if (path.startsWith("/login")) return "Вход · Букер";
  if (path.startsWith("/faq")) return "Помощь · Букер";
  if (path.startsWith("/deals/")) return "Deal Room · Букер";
  if (path.startsWith("/artists/")) return "Артист · Букер";
  if (path.startsWith("/venues/")) return "Площадка · Букер";
  if (path === "/legal") return "Правовые документы · Букер";
  if (path.startsWith("/legal/offer")) return "Оферта · Букер";
  if (path.startsWith("/legal/privacy")) return "Персональные данные · Букер";
  if (path.startsWith("/legal/cookies")) return "Cookie-файлы · Букер";
  if (path.startsWith("/legal/disputes")) return "Споры · Букер";
  if (path.startsWith("/legal/suppliers")) return "Исполнители · Букер";
  if (path.startsWith("/legal/cancellation")) return "Отмены · Букер";
  return DEFAULT_TITLE;
}

export function SiteChrome({ children }: { children: React.ReactNode }) {
  const [authed, setAuthed] = useState(false);
  const [admin, setAdmin] = useState(false);
  const [cabinetMode, setCabinetMode] = useState<CabinetMode | null>(null);
  const [notificationsOpen, setNotificationsOpen] = useState(false);
  const notificationsRef = useRef<HTMLSpanElement>(null);
  const [notifications, setNotifications] = useState<
    { id: string; subject?: string | null; body?: string | null }[]
  >([]);
  const path = usePathname();
  // Флаг студии зависит от window.location.search — считаем только после маунта,
  // иначе SSR и первая клиентская отрисовка расходятся (hydration mismatch).
  const [fullScreenStudio, setFullScreenStudio] = useState(false);

  useEffect(() => {
    if (!notificationsOpen) return;
    const closeOutside = (event: PointerEvent) => {
      if (!notificationsRef.current?.contains(event.target as Node)) setNotificationsOpen(false);
    };
    const closeOnEscape = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setNotificationsOpen(false);
        if (notificationsRef.current?.contains(document.activeElement)) notificationsRef.current.querySelector("button")?.focus();
      }
    };
    document.addEventListener("pointerdown", closeOutside);
    document.addEventListener("keydown", closeOnEscape);
    return () => { document.removeEventListener("pointerdown", closeOutside); document.removeEventListener("keydown", closeOnEscape); };
  }, [notificationsOpen]);

  useEffect(() => {
    setAuthed(Boolean(getToken()));
    setAdmin(sessionStorage.getItem("booker.demo.token") ? sessionStorage.getItem("booker.demo.admin") === "1" : localStorage.getItem(ADMIN_KEY) === "1");
    setNotificationsOpen(false);
  }, [path]);

  useEffect(() => {
    if (!getToken()) {
      setCabinetMode(null);
      return;
    }
    void api<{
      organizations?: { id: string; kind: string }[];
      active_organization_id?: string;
    }>("/me")
      .then((me) => {
        const activeOrgId = getActiveOrg() || me.active_organization_id || me.organizations?.[0]?.id;
        const org = me.organizations?.find((o) => o.id === activeOrgId) || me.organizations?.[0];
        setCabinetMode(org ? orgKindToCabinetMode(org.kind) : null);
      })
      .catch(() => setCabinetMode(null));
  }, [path, authed]);

  useEffect(() => {
    if (!authed || !getToken()) {
      setNotifications([]);
      setNotificationsOpen(false);
      return;
    }
    void api<{ items: { id: string; subject?: string | null; body?: string | null }[] }>("/notifications")
      .then((res) => setNotifications(res.items || []))
      .catch(() => setNotifications([]));
  }, [path, authed]);

  useEffect(() => {
    setFullScreenStudio(path === "/events/new" && isEventStudioMapV1());
  }, [path]);

  useEffect(() => {
    let title = tabTitle(path);
    if (path.startsWith("/search")) {
      const city = new URLSearchParams(window.location.search).get("city");
      title = city ? `Каталог — ${city} · Букер` : title;
    }
    document.title = title;
    if (getToken()) {
      trackClientEvent("page.view", { path });
    }
  }, [path]);

  useEffect(() => {
    if (fullScreenStudio) return;
    const onScroll = () => {
      const bar = document.getElementById("scroll-progress");
      if (!bar) return;
      const h = document.documentElement;
      const max = h.scrollHeight - h.clientHeight;
      const p = max > 0 ? Math.min(1, h.scrollTop / max) : 0;
      bar.style.transform = `scaleX(${p})`;
    };
    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => {
      window.removeEventListener("scroll", onScroll);
      const bar = document.getElementById("scroll-progress");
      bar?.style.removeProperty("transform");
    };
  }, [path, fullScreenStudio]);

  const isSupply = cabinetMode === "performer" || cabinetMode === "venue";
  const cabinetHref = cabinetMode ? `/cabinet/${cabinetMode}` : "/cabinet";
  const calendarHref = cabinetMode && isSupply ? supplyCalendarHref(cabinetMode) : cabinetHref;
  const requestsHref = cabinetMode && isSupply ? supplyRequestsHref(cabinetMode) : cabinetHref;
  const primaryWorkHref = isSupply ? calendarHref : "/events/new";
  const primaryWorkLabel = isSupply ? "Мой календарь" : "Создать заявку";
  const onCalendar = isSupply && path.includes("/calendar");
  const onRequests = isSupply && path.includes("/requests");

  if (fullScreenStudio) {
    return (
      <div id="content" key="event-studio-fullscreen" className="studio-fullscreen-root">
        <DemoBanner /><EditionToggle />{children}
      </div>
    );
  }

  return (
    <>
      <DemoBanner />
      <div id="scroll-progress" className="scroll-progress" aria-hidden />
      <a className="skip" href="#content">
        К содержанию
      </a>
      <div className="wrap">
        <header className="top surface-glass">
          <Link className="brand" href="/" aria-label="Букер">
            <BrandLockup />
            <span className="brand-tagline">Люди. Места. События.</span>
          </Link>
          <nav className={`nav-public${!authed ? " nav-reference-public" : ""}`} aria-label="Основное">
            {authed && !isSupply ? (
              <Link href="/search" aria-current={path.startsWith("/search") ? "page" : undefined}>
                Каталог
              </Link>
            ) : null}
            {authed ? (
              <Link
                href={primaryWorkHref}
                aria-current={
                  isSupply
                    ? onCalendar
                      ? "page"
                      : undefined
                    : path.startsWith("/events/new")
                      ? "page"
                      : undefined
                }
              >
                {primaryWorkLabel}
              </Link>
            ) : (
              <>
                <Link href="/search?kind=artist">Найти артиста</Link>
                <Link href="/briefs">Найти работу</Link>
                <Link href="/#process-title">Как это работает</Link>
              </>
            )}
            {authed ? (
              <Link
                href={isSupply ? requestsHref : cabinetHref}
                aria-current={
                  isSupply
                    ? onRequests
                      ? "page"
                      : undefined
                    : path.startsWith("/cabinet") || path.startsWith("/deals")
                      ? "page"
                      : undefined
                }
              >
                {isSupply ? "Заявки" : "Сделки"}
              </Link>
            ) : null}
            {authed ? (
              <Link href="/profile" aria-current={path.startsWith("/profile") ? "page" : undefined}>
                Профиль
              </Link>
            ) : null}
            {admin ? (
              <Link href="/admin" aria-current={path.startsWith("/admin") ? "page" : undefined}>
                Оператор
              </Link>
            ) : null}
            {authed ? (
              <span ref={notificationsRef} style={{ position: "relative" }}>
                <button
                  type="button"
                  className="linkish"
                  aria-expanded={notificationsOpen}
                  aria-controls="notification-list"
                  onClick={() => setNotificationsOpen((open) => !open)}
                >
                  Уведомления
                  {notifications.length > 0 ? (
                    <span className="chip wait" style={{ marginLeft: 6 }}>
                      {notifications.length}
                    </span>
                  ) : null}
                </button>
                {notificationsOpen ? (
                  <div
                    className="card surface-glass"
                    id="notification-list"
                    role="region"
                    aria-label="Уведомления"
                    style={{
                      position: "absolute",
                      right: 0,
                      top: "calc(100% + 8px)",
                      zIndex: 40,
                      width: 320,
                      maxHeight: 360,
                      overflow: "auto",
                      display: "grid",
                      gap: 8,
                      padding: 12,
                    }}
                  >
                    {notifications.length === 0 ? (
                      <p className="timeline">Пока пусто</p>
                    ) : (
                      notifications.map((item) => (
                        <div key={item.id}>
                          <strong>{item.subject || "Уведомление"}</strong>
                          {item.body ? <p className="timeline">{item.body}</p> : null}
                        </div>
                      ))
                    )}
                  </div>
                ) : null}
              </span>
            ) : null}
            {authed ? <WorkspaceSwitcher /> : null}
            {authed ? (
              <button
                type="button"
                className="linkish"
                onClick={() => {
                  setToken(null);
                  localStorage.removeItem(ADMIN_KEY);
                  window.location.href = "/";
                }}
              >
                Выйти
              </button>
            ) : null}
          </nav>
          <EditionToggle />
          <div className={`nav-mobile-auth${!authed ? " reference-login" : ""}`}>
            {authed ? (
              <button
                type="button"
                className="linkish"
                onClick={() => {
                  setToken(null);
                  localStorage.removeItem(ADMIN_KEY);
                  window.location.href = "/";
                }}
              >
                Выйти
              </button>
            ) : (
              <Link href={loginHref(path)}>Войти</Link>
            )}
          </div>
        </header>
        <div className={authed && /^\/(cabinet|profile|deals|briefs|compare|s)(\/|$)/.test(path) ? "workspace-layout" : undefined}>
          {authed && /^\/(cabinet|profile|deals|briefs|compare|s)(\/|$)/.test(path) && <WorkspaceNavigation mode={cabinetMode} admin={admin} />}
          <div id="content" className="site-content" data-section={path.split("/")[1] || "home"}>{children}</div>
        </div>
        <footer className="site-footer surface-glass reference-footer">
          <Link href="/" className="footer-brand" aria-label="Букер — главная"><BrandLockup /><span>Люди. Места. События.</span></Link>
          <nav aria-label="Информация о сервисе"><Link href="/dev/cabinets">Демо-кабинеты</Link><Link href="/legal/privacy">Конфиденциальность</Link><Link href="/legal">Документы</Link><Link href="/faq">Вопросы и ответы</Link><Link href="/support">Поддержка</Link></nav>
        </footer>
      </div>
      <nav className="bottom-nav surface-glass" aria-label="Мобильная навигация">
        <Link href="/" aria-label="Главная" className={path === "/" ? "on" : ""}>
          Главная
        </Link>
        <Link
          href={isSupply ? calendarHref : "/search"}
          className={
            isSupply
              ? onCalendar
                ? "on"
                : ""
              : path.startsWith("/search") || path.startsWith("/artists") || path.startsWith("/venues")
                ? "on"
                : ""
          }
        >
          {isSupply ? "Календарь" : "Каталог"}
        </Link>
        <Link
          href={authed ? (isSupply ? requestsHref : cabinetHref) : loginHref("/cabinet")}
          className={
            isSupply
              ? onRequests
                ? "on"
                : ""
              : path.startsWith("/cabinet") || path.startsWith("/deals")
                ? "on"
                : ""
          }
        >
          {isSupply ? "Заявки" : "Сделки"}
        </Link>
        <Link href={authed ? "/profile" : loginHref("/profile")} className={path.startsWith("/profile") ? "on" : ""}>
          Профиль
        </Link>
      </nav>
    </>
  );
}
