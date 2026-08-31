export const STATUS_LABEL: Record<string, string> = {
  Draft: "Черновик",
  RequestSent: "Заявка отправлена",
  Negotiation: "Согласование",
  DateHeld: "Дата удерживается",
  AwaitingContract: "Договор",
  AwaitingPayment: "Ожидается оплата",
  Confirmed: "Подтверждено",
  InProgress: "В работе",
  Completed: "Завершено",
  Cancelled: "Отмена",
  Dispute: "Спор",
  Resolved: "Решение оператора",
};

export const STAGE_ORDER = [
  "Negotiation",
  "DateHeld",
  "AwaitingContract",
  "AwaitingPayment",
  "Confirmed",
];

export function nextAction(status: string): { label: string; kind: string } {
  if (status === "Negotiation") return { label: "Кивнуть условиям", kind: "ack" };
  if (status === "DateHeld" || status === "AwaitingContract") return { label: "Достать договор", kind: "contract" };
  if (status === "AwaitingPayment") return { label: "К оплате", kind: "pay" };
  if (status === "Confirmed" || status === "InProgress") return { label: "Принять вечер", kind: "receive" };
  if (status === "Dispute") return { label: "Позвать человека", kind: "operator" };
  return { label: "Справка", kind: "help" };
}

export function nextActionHint(kind: string): string {
  if (kind === "ack") return "Подтвердите условия — обе стороны должны нажать «Кивнуть».";
  if (kind === "contract") return "Подпишите договор через OTP.";
  if (kind === "pay") return "Создайте счёт и внесите оплату.";
  if (kind === "receive") return "Дождитесь дня события.";
  if (kind === "operator") return "Оператор рассмотрит спор.";
  return "Проверьте статус сделки.";
}
