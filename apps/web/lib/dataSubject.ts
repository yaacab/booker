export type DataSubjectRequest = {
  id: string;
  request_type: string;
  status: string;
  state_version: number;
  subject_user_id?: string | null;
  created_at?: string | null;
  updated_at?: string | null;
  decision_reason_code?: string | null;
};

export type DataSubjectRequestDetail = DataSubjectRequest & {
  correction_field?: string | null;
  events?: { from_status: string | null; to_status: string; reason_code?: string | null; state_version: number; created_at: string | null }[];
  active_hold?: boolean;
  deletion_plan?: unknown;
};

export type DataSubjectList = { items: DataSubjectRequest[]; total?: number };

export function dataSubjectListPath(offset: number, admin = false, requestStatus = ""): string {
  const params = new URLSearchParams({ limit: "20", offset: String(offset) });
  if (admin && requestStatus) params.set("request_status", requestStatus);
  return `${admin ? "/admin" : ""}/data-subject/requests?${params}`;
}

export type DataSubjectDeletionPlan = {
  blocked?: boolean;
  dry_run?: boolean;
  executor_enabled?: boolean;
  block_reasons?: string[];
  categories?: { code: string; action: string; count: number | null }[];
};

export type DataSubjectHold = {
  id: string;
  scope: string;
  reason_code: string;
  released_at?: string | null;
};

export const DATA_SUBJECT_TRANSITIONS: Record<string, string[]> = {
  pending: ["in_review", "needs_info", "rejected"],
  in_review: ["needs_info", "approved", "rejected"],
  needs_info: ["in_review", "rejected"],
  approved: ["completed"],
};

export const DATA_SUBJECT_REASONS = [
  "review_started", "more_information", "scope_accepted", "scope_rejected", "policy_pending",
] as const;

export const DATA_SUBJECT_HOLD_REASONS = [
  "dispute", "security_incident", "financial_review", "other_review",
] as const;

export function availableDataSubjectTransitions(row: DataSubjectRequestDetail): string[] {
  return (DATA_SUBJECT_TRANSITIONS[row.status] || [])
    .filter((value) => value !== "completed" || row.request_type === "restrict")
    .filter((value) => value !== "approved" || row.request_type !== "delete" || !row.active_hold);
}

export function dataSubjectReasonForStatus(status: string): (typeof DATA_SUBJECT_REASONS)[number] {
  if (status === "needs_info") return "more_information";
  if (status === "approved" || status === "completed") return "scope_accepted";
  if (status === "rejected") return "scope_rejected";
  return "review_started";
}

export const DATA_SUBJECT_TYPES = ["access", "export", "restrict", "delete", "correct"] as const;

export function dataSubjectPath(id: string, admin = false, suffix = ""): string {
  return `${admin ? "/admin" : ""}/data-subject/requests/${encodeURIComponent(id)}${suffix}`;
}

export function dataSubjectHeaders(totp: string, version?: number, key?: string): Headers {
  const headers = new Headers();
  if (totp.trim()) headers.set("X-Booker-TOTP", totp.trim());
  if (version !== undefined) headers.set("If-Match", String(version));
  if (key) headers.set("Idempotency-Key", key);
  return headers;
}

export function dataSubjectStatusLabel(value: string): string {
  const labels: Record<string, string> = {
    pending: "Получен", in_review: "На рассмотрении", needs_info: "Нужны сведения",
    approved: "Одобрен", completed: "Завершён", rejected: "Отклонён",
    cancelled: "Отменён",
  };
  return labels[value] || "Статус уточняется";
}

export function dataSubjectTypeLabel(value: string): string {
  const labels: Record<string, string> = {
    access: "Доступ к данным", export: "Выгрузка данных", restrict: "Ограничение обработки",
    delete: "Удаление данных", correct: "Исправление данных",
  };
  return labels[value] || "Запрос по данным";
}

export function dataSubjectError(status: number): string {
  if (status === 409) return "Запрос изменился. Данные обновлены; проверьте их перед повторным действием.";
  if (status === 401 || status === 403) return "Доступ не подтверждён. Проверьте вход и, для оператора, код 2FA.";
  return "Не удалось выполнить действие. Проверьте соединение и попробуйте снова.";
}
