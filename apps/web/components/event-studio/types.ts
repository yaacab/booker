export type AvailabilityState = "available" | "tentative" | "hold" | "busy" | "on_request";

export type EventStudioDraft = {
  title: string;
  kind: string;
  city: string;
  date: string;
  startsAt: string;
  endsAt: string;
  guests: number;
  venueId?: string;
  talentIds: string[];
  requirements: string[];
  version: number;
};

export type TalentItem = {
  id: string;
  name: string;
  categoryCode: string;
  roleLabel: string;
  honorariumFrom: number | null;
  verified: boolean;
  availability: AvailabilityState;
  availabilityLabel: string;
  confirmedAt: string | null;
  initials: string;
  tone: string;
};

export type VenueItem = {
  id: string;
  name: string;
  city: string;
  honorariumFrom: number | null;
  availabilityLabel?: string;
};

export type BudgetHint = {
  minRub: number;
  maxRub: number;
  isEstimate: true;
};

export type SaveStatus = "saving" | "saved" | "error" | "offline";

export const STUDIO_STAGES = ["Основа", "Место", "Команда", "Детали", "Проверка"] as const;
export type StudioStage = (typeof STUDIO_STAGES)[number];

export const EMPTY_DRAFT: EventStudioDraft = {
  title: "",
  kind: "Свадьба",
  city: "Москва",
  date: "",
  startsAt: "17:00",
  endsAt: "23:30",
  guests: 80,
  talentIds: [],
  requirements: ["Звук и свет", "Кейтеринг"],
  version: 1,
};
