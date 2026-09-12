import { api } from "@/lib/api";
import { eventCommandKey } from "@/lib/eventCommands";
import { categoryLabel } from "@/lib/copy";
import { formatDay, initials } from "@/lib/format";
import type {
  AvailabilityState,
  EventStudioDraft,
  TalentItem,
  VenueItem,
} from "./types";
import { EMPTY_DRAFT } from "./types";

const DRAFT_KEY = "booker.eventStudioMapDraft";

export const EVENT_STUDIO_DRAFT_STORAGE_KEY = DRAFT_KEY;
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
  honorarium_from_rub?: number | null;
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

function availabilityOf(item: CatalogItem, date?: string): { state: AvailabilityState; label: string } {
  const slots = item.open_slots ?? 0;
  if (slots > 0 && item.verified) {
    const day = date ? formatDay(`${date}T12:00:00+03:00`) : "на дату";
    return { state: "available", label: `Свободен: ${day.split(",")[0]}` };
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
    honorariumFrom: item.honorarium_from_rub ?? null,
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
    honorariumFrom: item.honorarium_from_rub ?? null,
    availabilityLabel: synthetic ? "Календарь ориентировочный" : undefined,
  };
}

export async function loadCatalog(
  city: string,
  date: string,
  category?: string,
  signal?: AbortSignal,
): Promise<CatalogResponse> {
  const params = new URLSearchParams({ city });
  const iso = catalogDateParam(date);
  if (iso) params.set("date", iso);
  if (category) params.set("category", category);
  return api<CatalogResponse>(`/catalog/search?${params.toString()}`, { signal });
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

function eventInterval(draft: EventStudioDraft): { start: string; end: string } {
  if (!draft.date || !draft.startsAt || !draft.endsAt) throw new Error("Укажите дату, начало и окончание события");
  const start = new Date(`${draft.date}T${draft.startsAt}:00+03:00`);
  const end = new Date(`${draft.date}T${draft.endsAt}:00+03:00`);
  if (draft.endsNextDay) end.setUTCDate(end.getUTCDate() + 1);
  if (!Number.isFinite(start.getTime()) || !Number.isFinite(end.getTime()) || end <= start) throw new Error("Окончание должно быть позже начала. Для события после полуночи отметьте следующий день.");
  return { start: start.toISOString(), end: end.toISOString() };
}

export function newSubmitIdempotencyKey(): string {
  if (typeof crypto !== "undefined" && "randomUUID" in crypto) return crypto.randomUUID();
  return `esm-${Date.now()}-${Math.random().toString(36).slice(2)}`;
}

/** Stable submit key for this browser tab — survives remount / retry without minting a duplicate event. */
export function getOrCreateSubmitIdempotencyKey(): string {
  if (typeof window === "undefined") return newSubmitIdempotencyKey();
  const existing = sessionStorage.getItem(IDEMPOTENCY_KEY);
  if (existing) return existing;
  const key = newSubmitIdempotencyKey();
  sessionStorage.setItem(IDEMPOTENCY_KEY, key);
  return key;
}

export function clearSubmitIdempotency(): void {
  if (typeof window === "undefined") return;
  sessionStorage.removeItem(IDEMPOTENCY_KEY);
  sessionStorage.removeItem(`${IDEMPOTENCY_KEY}:result`);
}

export function peekSubmitIdempotencyResult(idempotencyKey: string): string | null {
  if (typeof window === "undefined") return null;
  const prev = sessionStorage.getItem(IDEMPOTENCY_KEY);
  const prevResult = sessionStorage.getItem(`${IDEMPOTENCY_KEY}:result`);
  if (prev === idempotencyKey && prevResult) return prevResult;
  return null;
}

export async function submitEventStudioDraft(
  draft: EventStudioDraft,
  idempotencyKey: string,
): Promise<{ eventId: string; reused: boolean }> {
  // A cached event ID cannot prove that every selected participant received the request.
  // Replay both create and individual request commands against durable server receipts.
  const interval = eventInterval(draft);
  const me = await api<{ organizations: { id: string; kind: string }[]; active_organization_id?: string }>("/me");
  const org = me.organizations.find((o) => o.id === me.active_organization_id && o.kind === "customer") || me.organizations.find((o) => o.kind === "customer");
  if (!org) throw new Error("Сначала войдите как заказчик");
  const selectedIds = [...new Set(draft.talentIds)];
  const selected = await Promise.all(selectedIds.map((id) => api<{ id: string; category: string }>(`/artists/${id}`)));
  const roleCounts = new Map<string, number>();
  for (const profile of selected) roleCounts.set(profile.category, (roleCounts.get(profile.category) || 0) + 1);
  const requirements = [...roleCounts.entries()].map(([category_code, qty]) => ({ category_code, qty }));
  if (draft.venueId) requirements.push({ category_code: "venue", qty: 1 });
  const payload = {
    organization_id: org.id,
    title: draft.title.trim() || draft.kind || "Событие",
    city: draft.city || "Москва",
    event_date: interval.start,
    ends_at: interval.end,
    event_type: draft.kind,
    guest_count: draft.guests,
    budget_rub: draft.budgetRub ?? null,
    requirements,
    notes: `требования:${draft.requirements.join(",")}`,
  };
  const created = await api<{ id: string; reused?: boolean; requirements: { id: string; category_code: string }[] }>("/events", {
    method: "POST", body: JSON.stringify({ ...payload, idempotency_key: await eventCommandKey(idempotencyKey, { payload, artistIds: selectedIds, venueId: draft.venueId || null }) }),
  });
  const reqByCategory = new Map((created.requirements || []).map((r) => [r.category_code, r.id]));
  const requests = [
    ...selected.map((profile) => ({ resource_type: "artist", resource_id: profile.id, requirement_id: reqByCategory.get(profile.category) })),
    ...(draft.venueId ? [{ resource_type: "venue", resource_id: draft.venueId, requirement_id: reqByCategory.get("venue") }] : []),
  ];
  for (const body of requests) {
    await api(`/events/${created.id}/requests`, { method: "POST", body: JSON.stringify({ ...body, idempotency_key: await eventCommandKey(created.id, body) }) });
  }
  sessionStorage.setItem(IDEMPOTENCY_KEY, idempotencyKey);
  sessionStorage.setItem(`${IDEMPOTENCY_KEY}:result`, created.id);
  clearStoredDraft();
  return { eventId: created.id, reused: Boolean(created.reused) };
}
