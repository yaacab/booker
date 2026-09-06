"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

const EXTRA_LINKS = [
  { href: "/cabinet/venue/halls", label: "Залы", match: (p: string) => p.includes("/halls") },
  { href: "/cabinet/venue/stats", label: "Статистика", match: (p: string) => p.includes("/stats") },
  {
    href: "/cabinet/venue/messages",
    label: "Сообщения",
    match: (p: string) => p.includes("/messages"),
  },
] as const;

/** Extra venue tabs (halls, stats, messages) — complements shared SupplyCabinetNav. */
export function VenueCabinetSubNav() {
  const path = usePathname() || "";

  return (
    <nav className="supply-cabinet-nav venue-cabinet-subnav" aria-label="Дополнительные разделы площадки">
      {EXTRA_LINKS.map((link) => {
        const on = link.match(path);
        return (
          <Link
            key={link.href}
            href={link.href}
            aria-current={on ? "page" : undefined}
            className={on ? "on" : undefined}
          >
            {link.label}
          </Link>
        );
      })}
    </nav>
  );
}
