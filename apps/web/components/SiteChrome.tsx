"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { usePathname } from "next/navigation";
import { BrandLockup } from "@/components/BrandLockup";
import { getToken, setToken } from "@/lib/api";
import { loginHref } from "@/lib/next";

const ADMIN_KEY = "booker.admin";
const DEFAULT_TITLE = "Букер — пока вы спорите в чате, дата уже чужая";

function tabTitle(path: string): string {
  if (path === "/") return DEFAULT_TITLE;
  if (path.startsWith("/search")) return "Кто ещё не занят · Букер";
  if (path.startsWith("/events/new")) return "Собрать вечер · Букер";
  if (path.startsWith("/cabinet")) return "Сделки · Букер";
  if (path.startsWith("/profile")) return "Профиль · Букер";
  if (path.startsWith("/admin")) return "Пульт · Букер";
  if (path.startsWith("/login")) return "Вход · Букер";
  if (path.startsWith("/faq")) return "Как это едет · Букер";
  if (path.startsWith("/deals/demo")) return "Гримёрка (демо) · Букер";
  if (path.startsWith("/deals/")) return "Гримёрка · Букер";
  if (path.startsWith("/artists/")) return "Артист · Букер";
  if (path.startsWith("/venues/")) return "Площадка · Букер";
  if (path === "/legal") return "Бумажки · Букер";
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
  const path = usePathname();

  useEffect(() => {
    setAuthed(Boolean(getToken()));
    setAdmin(localStorage.getItem(ADMIN_KEY) === "1");
  }, []);

  useEffect(() => {
    let title = tabTitle(path);
    if (path.startsWith("/search")) {
      const city = new URLSearchParams(window.location.search).get("city");
      title = city ? `Кто ещё не занят — ${city} · Букер` : title;
    }
    document.title = title;
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

  return (
    <>
      <div id="scroll-progress" className="scroll-progress" aria-hidden />
      <a className="skip" href="#content">
        К делу
      </a>
      <div className="wrap">
        <header className="top">
          <Link className="brand" href="/" aria-label="Букер">
            <BrandLockup />
          </Link>
          <nav className="nav-public" aria-label="Основное">
            <Link href="/search">Кто ещё не занят</Link>
            <Link href="/events/new">Вечер</Link>
            {authed ? <Link href="/cabinet">Сделки</Link> : null}
            {authed ? <Link href="/profile">Профиль</Link> : null}
            {admin ? <Link href="/admin">Оператор</Link> : null}
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
          <p>Мы не играем сет и не сдаём зал. Держим слот и бумажки, пока вы не передумали.</p>
          <p>
            <Link href="/legal/offer">Оферта</Link>
            {" · "}
            <Link href="/legal/privacy">Персональные данные</Link>
            {" · "}
            <Link href="/legal/disputes">Споры</Link>
            {" · "}
            <Link href="/legal/cookies">Cookie-файлы</Link>
            {" · "}
            <Link href="/faq">Как это едет</Link>
            {" · "}
            <a href="mailto:hello@bukergo.ru">hello@bukergo.ru</a>
          </p>
        </footer>
      </div>
      <nav className="bottom-nav" aria-label="Мобильная навигация">
        <Link href="/" aria-label="Букер" className={path === "/" ? "on" : ""}>
          <BrandLockup compact />
        </Link>
        <Link
          href="/search"
          className={
            path.startsWith("/search") || path.startsWith("/artists") || path.startsWith("/venues") ? "on" : ""
          }
        >
          Свободные
        </Link>
        <Link href="/events/new" className={path.startsWith("/events") ? "on" : ""}>
          Вечер
        </Link>
        <Link
          href={authed ? "/cabinet" : loginHref("/cabinet")}
          className={path.startsWith("/cabinet") || path.startsWith("/deals") ? "on" : ""}
        >
          Сделки
        </Link>
        <Link href={authed ? "/profile" : loginHref("/profile")} className={path.startsWith("/profile") ? "on" : ""}>
          Я
        </Link>
      </nav>
    </>
  );
}
