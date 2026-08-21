export const BOOKING_STATUSES = [
  "Draft",
  "RequestSent",
  "Negotiation",
  "DateHeld",
  "AwaitingContract",
  "AwaitingPayment",
  "Confirmed",
  "InProgress",
  "Completed",
  "Cancelled",
  "Dispute",
  "Resolved",
] as const;

export type BookingStatus = (typeof BOOKING_STATUSES)[number];

export const ORG_KINDS = ["customer", "artist", "venue"] as const;
export type OrgKind = (typeof ORG_KINDS)[number];

export const DEAL_ROOM_TABS = ["chat", "terms", "documents", "payments"] as const;

export type PriceBreakdown = {
  quote_id: string;
  honorarium_rub: number;
  commission_rate: number;
  commission_rub: number;
  total_rub: number;
  currency: "RUB";
};

export const BRAND = {
  name: "Букер",
  slug: "booker",
  tokens: {
    petrol: "#2D6A66",
    petrolHover: "#245853",
    gold: "#B58A46",
    graphite: "#151817",
    canvas: "#F3F0E9",
    cyan: "#18B8C9",
    success: "#159B68",
    warning: "#B7791F",
    danger: "#C24156",
  },
} as const;
