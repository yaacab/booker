/** Публичные подписи. Юридические страницы живут отдельно. */

export const CHIP = {
  verified: "профиль подтверждён",
  pending: "профиль не подтверждён",
  slotOk: "есть свободные даты",
  slotWait: "доступность уточняется",
  slotNone: "нет свободных дат",
  syntheticCalendar: "календарь ориентировочный",
  openDataVenue: "информация из открытых источников",
};

export const KIND_LABEL: Record<string, string> = {
  customer: "Заказчик",
  artist: "Исполнитель",
  venue: "Площадка",
  performer: "Исполнитель",
};

export const CATEGORY: Record<string, string> = {
  dj: "DJ",
  host: "Ведущий",
  cover: "Кавер",
  photo: "Фотограф",
  makeup: "Визажист",
  decor: "Декоратор",
  catering: "Кейтеринг",
  venue: "Площадка",
};

export function categoryLabel(id?: string | null): string {
  if (!id) return "";
  return CATEGORY[id] || id;
}

/** Пилот. В выдаче сейчас только эти города. */
export const PILOT_CITIES = ["Москва"] as const;
