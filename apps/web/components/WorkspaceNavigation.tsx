"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import type { CabinetMode } from "@/lib/cabinetRoutes";

/** Навигация отображает существующие маршруты; доступ проверяют страницы и API. */
export function WorkspaceNavigation({ mode, admin }: { mode: CabinetMode | null; admin: boolean }) {
  const path = usePathname();
  const role = mode || "customer";
  const root = `/cabinet/${role}`;
  const links = role === "customer"
    ? [[root,"Обзор"],[`${root}/messages`,"Сообщения"],[`${root}/favorites`,"Избранное"],[`${root}/saved-searches`,"Сохранённый поиск"],["/briefs","Публичные брифы"]]
    : [[root,"Обзор"],[`${root}/calendar`,"Календарь"],[`${root}/requests`,"Заявки"],[`${root}/messages`,"Сообщения"],...(role === "venue" ? [[`${root}/halls`,"Залы"],[`${root}/stats`,"Статистика"]] : [[`${root}/services`,"Услуги"]])];
  return <aside className="workspace-sidebar">
    <p className="workspace-nav-caption">Ваше пространство</p>
    <nav aria-label="Навигация рабочего пространства">
      {links.map(([href,label]) => <Link key={href} href={href} aria-current={path === href ? "page" : undefined}>{label}</Link>)}
      <Link href="/profile" aria-current={path === "/profile" ? "page" : undefined}>Профиль и настройки</Link>
      {admin && <Link href="/admin" aria-current={path === "/admin" ? "page" : undefined}>Панель оператора</Link>}
    </nav>
    <div className="workspace-help"><strong>Всё для вашего события</strong><p>Договорённости и переписка сохраняются в сделке.</p><Link href="/support">Нужна помощь?</Link></div>
  </aside>;
}
