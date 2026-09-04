export type PerformerRequest = {
  id: string;
  status: string;
  event_title: string;
  event_date: string | null;
  offer_id: string | null;
  booking_id: string | null;
  slot_id: string | null;
  honorarium_rub: number;
};

export type PerformerBooking = {
  id: string;
  status: string;
  event_title: string;
  event_date?: string;
};

export type PerformerDealRoom = {
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
};

export type CalendarConflict = {
  booking_id: string;
  event_title: string;
  event_date: string;
  conflict_with: string;
  conflict_booking_id: string;
};
