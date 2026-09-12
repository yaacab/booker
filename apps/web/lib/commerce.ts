import { ApiError } from "./api";

export type Audience = "artist" | "venue" | "customer";
export type CommercialPlan = {
  code: string; audience: Audience; title: string;
  monthly_price_rub: number; annual_price_rub: number; annual_savings_rub: number;
  supplier_fee_bps: number; customer_fee_bps: number;
  features: Record<string, boolean | number>; feature_labels: Record<string, string>;
  version: number; commercial_policy_version: string; currency: string; sort_order: number;
};
export type BillingOrder = {
  id: string; organization_id: string; product_kind: string; product_code: string;
  amount_rub: number; currency: string; status: string; provider: string;
  test_mode: boolean; checkout_url: string | null; checkout_available: boolean;
  billing_period: string; created_at: string; paid_at: string | null; message: string | null;
};
export type CommerceCatalog = {
  promotions: { code: string; audience: "artist" | "venue"; title: string; price_rub: number; duration_hours: number; version: number }[];
  plans: CommercialPlan[]; checkout_available: boolean; test_mode: boolean;
  flags: Record<string, boolean>;
};
export type CommerceState = {
  plan: CommercialPlan; features: Record<string, boolean | number>; can_manage: boolean;
  subscription: null | {
    plan_code: string; status: string; current_period_end: string;
    cancel_at_period_end: boolean; next_plan_code: string | null;
  };
  orders: BillingOrder[];
};
export type CommerceOrg = { id: string; name: string; kind: Audience; role: string };
export type CommerceMe = { organizations: CommerceOrg[]; active_organization_id?: string };
export const AUDIENCES: { code: Audience; label: string }[] = [
  { code: "artist", label: "Исполнитель" }, { code: "venue", label: "Площадка" },
  { code: "customer", label: "Организатор" },
];
export const ORDER_STATUS: Record<string, string> = {
  created: "Ожидает подключения оплаты", pending_payment: "Ожидает оплаты", paid: "Оплачен",
  failed: "Оплата не прошла", cancelled: "Отменён", refunded: "Возвращён",
};
export function feePercent(bps: number): string {
  return new Intl.NumberFormat("ru-RU", { style: "percent", maximumFractionDigits: 2 }).format(bps / 10000);
}
export function commerceError(error: unknown): string {
  if (error instanceof ApiError && !error.message.startsWith("{") && !error.message.startsWith("[")) return error.message;
  return "Не удалось загрузить или сохранить данные. Попробуйте ещё раз.";
}
export function commerceHref(audience: Audience): string {
  return audience === "artist" ? "/cabinet/performer/growth" : audience === "venue" ? "/cabinet/venue/growth" : "/cabinet/customer/business";
}
