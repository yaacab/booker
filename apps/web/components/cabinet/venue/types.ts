export type VenueRequest = {
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

export type VenueBooking = {
  id: string;
  status: string;
  event_title: string;
  event_date?: string;
};

export type VenueDealRoom = {
  booking_id: string;
  event_title: string;
  status: string;
  quote: {
    quote_id: string;
    honorarium_rub: number;
    total_rub: number;
    customer_ack: boolean;
    supplier_ack: boolean;
  };
  hold?: { status: string; expires_at: string } | null;
};

export type ProfileCompleteness = {
  score: number;
  items: { id: string; label: string; done: boolean }[];
  applicable?: boolean;
  publication_enabled?: boolean;
  publication_eligible?: boolean;
  publication_reason_codes?: string[];
};

export type VenuePhoto = {
  id?: string;
  url?: string;
  photo_url?: string;
  source_url?: string;
  rights_status?: string;
};

export type VenueProfile = {
  id: string;
  organization_id?: string;
  name: string;
  city: string;
  capacity?: number;
  verified: boolean;
  photos: VenuePhoto[];
  publication_enabled?: boolean;
  publication_state_version?: number;
  publication_eligible?: boolean;
  publication_reason_codes?: string[];
  calendar_confirmed_through?: string | null;
};

export type CalendarConflict = {
  booking_id: string;
  event_title: string;
  event_date: string;
  conflict_with: string;
  conflict_booking_id: string;
};

export type VenueHallTarget = {
  resource_type: string;
  resource_id: string;
  label: string;
  venue_id?: string;
};

export type VenueHall = {
  id: string;
  name: string;
  capacity: number;
};

export type VenueBookingStats = {
  total: number;
  confirmed: number;
  inProgress: number;
  negotiation: number;
  upcoming: number;
  completed: number;
  cancelled: number;
};
