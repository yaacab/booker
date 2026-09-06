export type CabinetMode = "customer" | "performer" | "venue";

export type OrgKind = "customer" | "artist" | "venue";

/** API organization.kind → UI cabinet route segment */
export function orgKindToCabinetMode(kind: string): CabinetMode | null {
  if (kind === "customer") return "customer";
  if (kind === "artist") return "performer";
  if (kind === "venue") return "venue";
  return null;
}

export function cabinetPathForKind(kind: string): string {
  const mode = orgKindToCabinetMode(kind);
  return mode ? `/cabinet/${mode}` : "/cabinet/customer";
}

export function cabinetPathForMode(mode: CabinetMode): string {
  return `/cabinet/${mode}`;
}

export type CabinetSection =
  | "home"
  | "calendar"
  | "requests"
  | "halls"
  | "events"
  | "offers"
  | "messages"
  | "stats"
  | "services"
  | "showcase";

export function cabinetSectionPath(mode: CabinetMode, section: CabinetSection): string {
  if (section === "home") return cabinetPathForMode(mode);
  return `/cabinet/${mode}/${section}`;
}

/** Supply calendar tab — must not share URL with requests (E16). */
export function supplyCalendarHref(mode: CabinetMode): string {
  return cabinetSectionPath(mode, "calendar");
}

/** Supply inbound requests tab. */
export function supplyRequestsHref(mode: CabinetMode): string {
  return cabinetSectionPath(mode, "requests");
}

export function isSupplyCabinet(mode: CabinetMode): boolean {
  return mode === "performer" || mode === "venue";
}

export function cabinetTitle(mode: CabinetMode): string {
  if (mode === "customer") return "Кабинет заказчика";
  if (mode === "performer") return "Кабинет исполнителя";
  return "Кабинет площадки";
}

export function cabinetHeadline(mode: CabinetMode): string {
  if (mode === "customer") return "Студия событий";
  if (mode === "performer") return "Календарь исполнителя";
  return "Пульт площадки";
}
