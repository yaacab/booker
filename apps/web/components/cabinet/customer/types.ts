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

export type CustomerDealRoom = import("../DealCard").CabinetDeal;
