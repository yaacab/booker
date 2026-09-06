"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  type CabinetMode,
  cabinetPathForMode,
  supplyCalendarHref,
  supplyRequestsHref,
} from "@/lib/cabinetRoutes";

type Props = {
  mode: CabinetMode;
};

/** Distinct calendar vs requests destinations for supply cabinets (E16). */
export function SupplyCabinetNav({ mode }: Props) {
  const path = usePathname() || "";
  const home = cabinetPathForMode(mode);
  const calendar = supplyCalendarHref(mode);
  const requests = supplyRequestsHref(mode);
  const onHome = path === home;
  const onCalendar = path.includes("/calendar");
  const onRequests = path.includes("/requests");

  return (
    <nav className="supply-cabinet-nav" aria-label="Разделы кабинета">
      <Link href={home} aria-current={onHome ? "page" : undefined} className={onHome ? "on" : undefined}>
        Обзор
      </Link>
      <Link
        href={calendar}
        aria-current={onCalendar ? "page" : undefined}
        className={onCalendar ? "on" : undefined}
      >
        Календарь
      </Link>
      <Link
        href={requests}
        aria-current={onRequests ? "page" : undefined}
        className={onRequests ? "on" : undefined}
      >
        Заявки
      </Link>
    </nav>
  );
}
