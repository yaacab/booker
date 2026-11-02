export type PerformerRequest = {
  id: string;
  status: string;
  event_title: string;
  event_date: string | null;
  offer_id: string | null;
  booking_id: string | null;
  slot_id: string | null;
  honorarium_rub: number | null; // the supplier's own catalogue tariff; null = no tariff, the supplier enters the amount
  honorarium_source?: "tariff" | "none";
  event_city?: string | null;
  guest_count?: number | null;
  budget_rub?: number | null; // the customer's limit, not a price
  customer_name?: string | null;
  brief?: { rider: string[]; wishes: string; hall: string | null };
};

export type PerformerBooking = {
  id: string;
  status: string;
  event_title: string;
  event_date?: string;
};

export type PerformerDealRoom = import("../DealCard").CabinetDeal;

export type ProfileCompleteness = {
  score: number;
  items: { id: string; label: string; done: boolean }[];
  applicable?: boolean;
  eligible?: boolean;
  reason_codes?: string[];
  resource_type?: "artist" | "venue";
  resource_id?: string;
  publication_enabled?: boolean;
  publication_state_version?: number;
};

export type CalendarConflict = {
  booking_id: string;
  event_title: string;
  event_date: string;
  conflict_with: string;
  conflict_booking_id: string;
};

export type PerformerService = {
  id: string;
  title: string;
  category_code: string;
  description: string;
  honorarium_rub: number | null;
};

export type PerformerArtistProfile = {
  id: string;
  name: string;
  city: string;
  category: string;
  verified: boolean;
  media_url: string | null;
  rider: Record<string, string>;
  tariffs: { id: string; title: string; honorarium_rub: number }[];
  slots: { id: string; status: string; starts_at: string; ends_at: string }[];
  publication_enabled?: boolean;
  publication_state_version?: number;
  publication_eligible?: boolean;
  publication_reason_codes?: string[];
};

export type PerformerVacationItem = {
  resource_type: string;
  resource_id: string;
  label: string;
  active: boolean;
  starts_at: string | null;
  ends_at: string | null;
};
