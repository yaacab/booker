export type SupportQueueFilters = {
  state: string;
  overdue: boolean;
  escalated: boolean;
  priority: string;
  category: string;
  assignedToMe: boolean;
  limit: number;
  offset: number;
};

export type SupportTicket = {
  id: string;
  ticket_number: string;
  subject: string;
  category: string;
  status: string;
  priority: string;
  assigned_to_user_id?: string | null;
  accepted_by_user_id?: string | null;
  accepted_at?: string | null;
  state_version: number;
  response_due_at?: string | null;
  response_overdue?: boolean;
  overdue_escalated_at?: string | null;
  first_response_late?: boolean;
  has_operator_response?: boolean;
  reopened_at?: string | null;
  created_at?: string | null;
};

export type SupportTicketDetail = SupportTicket & {
  body: string;
  messages: { id: string; author_kind: string; actor_user_id: string; actor_name: string; body: string; created_at: string | null }[];
  system_events: { id: string; action: string; actor_user_id: string | null; created_at: string | null }[];
  system_events_truncated: boolean;
};

export type SupportNote = {
  id: string;
  author_user_id: string;
  body: string;
  created_at: string | null;
};

export function supportQueuePath(filters: SupportQueueFilters): string {
  const params = new URLSearchParams({
    state: filters.state,
    overdue_only: String(filters.overdue),
    escalated_only: String(filters.escalated),
    assigned_to_me: String(filters.assignedToMe),
    limit: String(filters.limit),
    offset: String(filters.offset),
  });
  if (filters.priority !== "all") params.set("priority", filters.priority);
  if (filters.category !== "all") params.set("category", filters.category);
  return `/admin/support/tickets?${params.toString()}`;
}

export function supportTicketPath(id: string, suffix = ""): string {
  return `/admin/support/tickets/${encodeURIComponent(id)}${suffix}`;
}

export function supportQueueHeaders(totp: string, version?: number, key?: string): Headers {
  const headers = new Headers();
  if (totp.trim()) headers.set("X-Booker-TOTP", totp.trim());
  if (version !== undefined) headers.set("If-Match", String(version));
  if (key) headers.set("Idempotency-Key", key);
  return headers;
}

export type StableSupportKey = { signature: string; key: string };

export function stableSupportKey(
  current: StableSupportKey | null,
  signature: string,
  makeKey: () => string,
): StableSupportKey {
  return current?.signature === signature ? current : { signature, key: makeKey() };
}

export function safeSupportSubject(subject: string): string {
  const clean = subject.replace(/[\u0000-\u001f\u007f-\u009f]/g, " ").replace(/\s+/g, " ").trim();
  return clean.length > 120 ? `${clean.slice(0, 119)}…` : clean || "Без темы";
}

export function supportQueueAge(createdAt: string | null | undefined, now = Date.now()): string {
  const timestamp = createdAt ? Date.parse(createdAt) : NaN;
  if (!Number.isFinite(timestamp)) return "Возраст неизвестен";
  const minutes = Math.max(0, Math.floor((now - timestamp) / 60_000));
  if (minutes < 60) return `${minutes} мин`;
  const hours = Math.floor(minutes / 60);
  if (hours < 24) return `${hours} ч ${minutes % 60} мин`;
  return `${Math.floor(hours / 24)} д ${hours % 24} ч`;
}
