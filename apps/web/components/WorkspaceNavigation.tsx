"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import type { CabinetMode } from "@/lib/cabinetRoutes";

function NavigationIcon({ href }: { href: string }) {
  const shape = href.includes("calendar") ? <><rect x="3" y="5" width="18" height="16" rx="3" /><path d="M7 3v4m10-4v4M3 11h18" /></>
    : href.includes("message") ? <path d="M5 4h14a2 2 0 0 1 2 2v10a2 2 0 0 1-2 2H9l-5 3v-3a2 2 0 0 1-2-2V6a2 2 0 0 1 3-2Z" />
    : href.includes("favorites") ? <path d="m12 20-8-8C-2 5 7 0 12 7c5-7 14-2 8 5Z" />
    : href.includes("profile") ? <><circle cx="12" cy="8" r="4" /><path d="M4 21v-2a8 8 0 0 1 16 0v2" /></>
    : href.includes("requests") || href.includes("briefs") ? <><rect x="5" y="3" width="14" height="18" rx="2" /><path d="M9 8h6m-6 4h6m-6 4h4" /></>
    : href.includes("search") ? <><circle cx="10" cy="10" r="6" /><path d="m15 15 6 6" /></>
    : <><rect x="3" y="3" width="7" height="7" rx="2" /><rect x="14" y="3" width="7" height="7" rx="2" /><rect x="3" y="14" width="7" height="7" rx="2" /><rect x="14" y="14" width="7" height="7" rx="2" /></>;
  return <svg width="19" height="19" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.6" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">{shape}</svg>;
}

/** Навигация отображает существующие маршруты; доступ проверяют страницы и API. */
export function WorkspaceNavigation({ mode, admin }: { mode: CabinetMode | null; admin: boolean }) {
  const path = usePathname();
  const role = mode;
  const root = `/cabinet/${role}`;
  const links = !role ? [["/cabinet", "Моё пространство"]] : role === "customer"
    ? [[root,"Обзор"],[`${root}/messages`,"Сообщения"],[`${root}/favorites`,"Избранное"],[`${root}/saved-searches`,"Сохранённый поиск"],["/briefs","Публичные брифы"]]
    : [[root,"Обзор"],[`${root}/calendar`,"Календарь"],[`${root}/requests`,"Заявки"],[`${root}/messages`,"Сообщения"],...(role === "venue" ? [[`${root}/halls`,"Залы"],[`${root}/stats`,"Статистика"]] : [[`${root}/services`,"Услуги"]])];
  return <aside className="workspace-sidebar">
    <p className="workspace-nav-caption">Ваше пространство</p>
    <nav aria-label="Навигация рабочего пространства">
      {links.map(([href,label]) => <Link key={href} href={href} aria-current={path === href ? "page" : undefined}><NavigationIcon href={href} /><span>{label}</span></Link>)}
      <Link href="/profile" aria-current={path === "/profile" ? "page" : undefined}><NavigationIcon href="/profile" /><span>Профиль и настройки</span></Link>
      {admin && <Link href="/admin" aria-current={path === "/admin" ? "page" : undefined}><NavigationIcon href="/admin" /><span>Панель оператора</span></Link>}
    </nav>
    <div className="workspace-help"><strong>Всё для вашего события</strong><p>Договорённости и переписка сохраняются в сделке.</p><Link href="/support">Нужна помощь?</Link></div>
  </aside>;
}
