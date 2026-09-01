"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { usePathname } from "next/navigation";
import { BrandLockup } from "@/components/BrandLockup";
import { WorkspaceSwitcher } from "@/components/WorkspaceSwitcher";
import { getToken, setToken, trackClientEvent } from "@/lib/api";
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
  if (path.startsWith("/deals/demo")) return "Deal Room (демо) · Букер";
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
  const [fullScreenStudio, setFullScreenStudio] = useState(false);
  const path = usePathname();

  useEffect(() => {
    setAuthed(Boolean(getToken()));
    setAdmin(localStorage.getItem(ADMIN_KEY) === "1");
  }, []);

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
    const bar = document.getElementById("scroll-progress");
    const onScroll = () => {
      const h = document.documentElement;
      const max = h.scrollHeight - h.clientHeight;
      const p = max > 0 ? Math.min(1, h.scrollTop / max) : 0;
      if (bar) bar.style.transform = `scaleX(${p})`;
    };
    onScroll();
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => window.removeEventListener("scroll", onScroll);
  }, [path]);

  if (fullScreenStudio) {
    return <div id="content">{children}</div>;
  }

  return (
    <>
      <div id="scroll-progress" className="scroll-progress" aria-hidden />
      <a className="skip" href="#content">
        К содержанию
      </a>
      <div className="wrap">
        <header className="top">
          <Link className="brand" href="/" aria-label="Букер">
            <BrandLockup />
          </Link>
          <nav className="nav-public" aria-label="Основное">
            <Link href="/search" aria-current={path.startsWith("/search") ? "page" : undefined}>Каталог</Link>
            <Link href="/events/new" aria-current={path.startsWith("/events/new") ? "page" : undefined}>Создать заявку</Link>
            {authed ? <Link href="/cabinet" aria-current={path.startsWith("/cabinet") || path.startsWith("/deals") ? "page" : undefined}>Сделки</Link> : null}
            {authed ? <Link href="/profile" aria-current={path.startsWith("/profile") ? "page" : undefined}>Профиль</Link> : null}
            {admin ? <Link href="/admin" aria-current={path.startsWith("/admin") ? "page" : undefined}>Оператор</Link> : null}
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
            ) : (
              <Link href={loginHref(path)}>Войти</Link>
            )}
          </nav>
          <div className="nav-mobile-auth">
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
        <div id="content">{children}</div>
        <footer className="site-footer">
          <p>Букер объединяет заявку, свободный слот, предложение и подтверждения в одном рабочем пространстве.</p>
          <p>
            <Link href="/legal/offer">Оферта</Link>
            {" · "}
            <Link href="/legal/privacy">Персональные данные</Link>
            {" · "}
            <Link href="/legal/disputes">Споры</Link>
            {" · "}
            <Link href="/legal/cookies">Cookie-файлы</Link>
            {" · "}
            <Link href="/faq">Помощь</Link>
            {" · "}
            <a href="mailto:hello@bukergo.ru">hello@bukergo.ru</a>
          </p>
        </footer>
      </div>
      <nav className="bottom-nav" aria-label="Мобильная навигация">
        <Link href="/" aria-label="Главная" className={path === "/" ? "on" : ""}>
          Главная
        </Link>
        <Link
          href="/search"
          className={
            path.startsWith("/search") || path.startsWith("/artists") || path.startsWith("/venues") ? "on" : ""
          }
        >
          Каталог
        </Link>
        <Link
          href={authed ? "/cabinet" : loginHref("/cabinet")}
          className={path.startsWith("/cabinet") || path.startsWith("/deals") ? "on" : ""}
        >
          Сделки
        </Link>
        <Link href={authed ? "/profile" : loginHref("/profile")} className={path.startsWith("/profile") ? "on" : ""}>
          Профиль
        </Link>
      </nav>
    </>
  );
}
