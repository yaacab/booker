export type CustomerEvent = {
  id: string;
  title: string;
  status: string;
  event_date: string;
  city?: string;
};

export type CustomerBooking = {
  id: string;
  status: string;
  event_title: string;
  event_date?: string;
};

export type CustomerDealRoom = {
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
