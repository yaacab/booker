import { api } from "@/lib/api";
import { categoryLabel } from "@/lib/copy";
import { formatDay, initials, moscowToday } from "@/lib/format";
import type {
  AvailabilityState,
  BudgetHint,
  EventStudioDraft,
  TalentItem,
  VenueItem,
} from "./types";
import { EMPTY_DRAFT } from "./types";

const DRAFT_KEY = "booker.eventStudioMapDraft";
const IDEMPOTENCY_KEY = "booker.eventStudioSubmitKey";

type CatalogItem = {
  id: string;
  name: string;
  city: string;
  category: string;
  verified?: boolean;
  open_slots?: number;
  next_open_at?: string | null;
  tariffs?: { honorarium_rub: number }[];
  availability_mode?: string;
};

type CatalogResponse = {
  items: CatalogItem[];
  venues: CatalogItem[];
};

const TONE_BY_CATEGORY: Record<string, string> = {
  host: "emerald",
  dj: "graphite",
  photo: "gold",
  decor: "rose",
  cover: "emerald",
  makeup: "rose",
};

function minHonorarium(tariffs?: { honorarium_rub: number }[]): number | null {
  if (!tariffs?.length) return null;
  return Math.min(...tariffs.map((t) => t.honorarium_rub));
}

function availabilityOf(item: CatalogItem, date?: string): { state: AvailabilityState; label: string } {
  const slots = item.open_slots ?? 0;
  if (slots > 0 && item.verified) {
    const day = date ? formatDay(`${date}T12:00:00+03:00`) : "на дату";
    return { state: "available", label: `● Свободен ${day.split(",")[0]}` };
  }
  if (slots > 0 && !item.verified) {
    return { state: "tentative", label: "● Нужно уточнить слот" };
  }
  if (item.next_open_at) {
    return { state: "busy", label: "● Занят на выбранную дату" };
  }
  return { state: "on_request", label: "● По запросу" };
}

function catalogDateParam(date: string): string | undefined {
  if (!date) return undefined;
  return `${date}T00:00:00+03:00`;
}

export function mapCatalogTalent(item: CatalogItem, date?: string): TalentItem {
  const avail = availabilityOf(item, date);
  return {
    id: item.id,
    name: item.name,
    categoryCode: item.category,
    roleLabel: categoryLabel(item.category) || item.category,
    honorariumFrom: minHonorarium(item.tariffs),
    verified: Boolean(item.verified),
    availability: avail.state,
    availabilityLabel: avail.label,
    confirmedAt: item.next_open_at ?? null,
    initials: initials(item.name),
    tone: TONE_BY_CATEGORY[item.category] || "emerald",
  };
}

export function mapCatalogVenue(item: CatalogItem): VenueItem {
  const synthetic = item.availability_mode === "synthetic";
  return {
    id: item.id,
    name: item.name,
    city: item.city,
    honorariumFrom: minHonorarium(item.tariffs),
    availabilityLabel: synthetic ? "Календарь ориентировочный" : undefined,
  };
}

export async function loadCatalog(city: string, date: string, category?: string): Promise<CatalogResponse> {
  const params = new URLSearchParams({ city });
  const iso = catalogDateParam(date);
  if (iso) params.set("date", iso);
  if (category) params.set("category", category);
  return api<CatalogResponse>(`/catalog/search?${params.toString()}`);
}

export function budgetHintFromSelection(
  talents: TalentItem[],
  venues: VenueItem[],
  draft: EventStudioDraft,
): BudgetHint | null {
  const selectedTalents = talents.filter((t) => draft.talentIds.includes(t.id));
  const venue = venues.find((v) => v.id === draft.venueId);
  const amounts = [
    ...selectedTalents.map((t) => t.honorariumFrom).filter((n): n is number => n != null),
    ...(venue?.honorariumFrom != null ? [venue.honorariumFrom] : []),
  ];
  if (!amounts.length) return null;
  const minRub = amounts.reduce((sum, n) => sum + n, 0);
  return { minRub, maxRub: Math.round(minRub * 1.28), isEstimate: true };
}

export type StoredDraft = {
  draft: EventStudioDraft;
  savedAt: string;
};

export function loadStoredDraft(): StoredDraft | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = localStorage.getItem(DRAFT_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as StoredDraft;
    if (!parsed.draft) return null;
    return {
      draft: { ...EMPTY_DRAFT, ...parsed.draft },
      savedAt: parsed.savedAt || new Date().toISOString(),
    };
  } catch {
    return null;
  }
}

export function saveStoredDraft(draft: EventStudioDraft): StoredDraft {
  const payload: StoredDraft = { draft, savedAt: new Date().toISOString() };
  localStorage.setItem(DRAFT_KEY, JSON.stringify(payload));
  return payload;
}

export function clearStoredDraft(): void {
  localStorage.removeItem(DRAFT_KEY);
}

export function bumpDraftVersion(draft: EventStudioDraft): EventStudioDraft {
  return { ...draft, version: (draft.version || 1) + 1 };
}

export function isDraftVersionConflict(local: EventStudioDraft, incoming: EventStudioDraft): boolean {
  return Boolean(incoming.version && local.version && incoming.version < local.version);
}

function eventIso(draft: EventStudioDraft): string {
  const base = draft.date || moscowToday();
  const time = draft.startsAt || "12:00";
  return new Date(`${base}T${time}:00+03:00`).toISOString();
}

function talentCategoryCodes(talentIds: string[], talents: TalentItem[]): Map<string, number> {
  const counts = new Map<string, number>();
  for (const id of talentIds) {
    const t = talents.find((item) => item.id === id);
    if (!t) continue;
    counts.set(t.categoryCode, (counts.get(t.categoryCode) || 0) + 1);
  }
  return counts;
}

export async function submitEventStudioDraft(
  draft: EventStudioDraft,
  talents: TalentItem[],
  idempotencyKey: string,
): Promise<{ eventId: string; reused: boolean }> {
  const prev = sessionStorage.getItem(IDEMPOTENCY_KEY);
  const prevResult = sessionStorage.getItem(`${IDEMPOTENCY_KEY}:result`);
  if (prev === idempotencyKey && prevResult) {
    return { eventId: prevResult, reused: true };
  }

  const me = await api<{ organizations: { id: string; kind: string }[]; active_organization_id?: string }>("/me");
  const org =
    me.organizations.find((o) => o.id === me.active_organization_id && o.kind === "customer") ||
    me.organizations.find((o) => o.kind === "customer") ||
    me.organizations[0];
  if (!org) throw new Error("Сначала войдите как заказчик");

  const roleCounts = talentCategoryCodes(draft.talentIds, talents);
  const requirements = [...roleCounts.entries()].map(([category_code, qty]) => ({ category_code, qty }));
  if (draft.venueId) requirements.push({ category_code: "venue", qty: 1 });

  const created = await api<{ id: string; requirements?: { id: string; category_code: string }[] }>("/events", {
    method: "POST",
    body: JSON.stringify({
      organization_id: org.id,
      title: draft.title.trim() || draft.kind || "Событие",
      city: draft.city || "Москва",
      event_date: eventIso(draft),
      guest_count: draft.guests || 50,
      budget_rub: null,
      requirements,
      notes: [
        `формат:${draft.kind}`,
        draft.date ? `дата:${draft.date}` : "дата:позже",
        `состав:${draft.talentIds.length || 0}`,
        draft.venueId ? `площадка:${draft.venueId}` : "площадка:не выбрана",
        `требования:${draft.requirements.join(",")}`,
        `idempotency:${idempotencyKey}`,
      ].join("; "),
    }),
  });

  const reqByCategory = new Map((created.requirements || []).map((r) => [r.category_code, r.id]));
  for (const talentId of draft.talentIds) {
    const talent = talents.find((t) => t.id === talentId);
    if (!talent) continue;
    await api(`/events/${created.id}/requests`, {
      method: "POST",
      body: JSON.stringify({
        resource_type: "artist",
        resource_id: talentId,
        requirement_id: reqByCategory.get(talent.categoryCode) || undefined,
      }),
    });
  }
  if (draft.venueId) {
    await api(`/events/${created.id}/requests`, {
      method: "POST",
      body: JSON.stringify({
        resource_type: "venue",
        resource_id: draft.venueId,
        requirement_id: reqByCategory.get("venue") || undefined,
      }),
    });
  }

  sessionStorage.setItem(IDEMPOTENCY_KEY, idempotencyKey);
  sessionStorage.setItem(`${IDEMPOTENCY_KEY}:result`, created.id);
  clearStoredDraft();
  return { eventId: created.id, reused: false };
}

export function newSubmitIdempotencyKey(): string {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) return crypto.randomUUID();
  return `esm-${Date.now()}-${Math.random().toString(36).slice(2)}`;
}
