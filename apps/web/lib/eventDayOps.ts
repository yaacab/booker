export type EventRequestLite = {
  id: string;
  status: string;
  requirement_id?: string | null;
  booking_id?: string | null;
  quote_id?: string | null;
};

export type RequirementLite = {
  id?: string;
  category_code: string;
  role_label?: string;
  qty?: number;
};

export type RoleBlocker = "no_request" | "no_offer" | "no_booking";

export const BLOCKER_LABEL: Record<RoleBlocker, string> = {
  no_request: "нет заявки",
  no_offer: "нет оффера",
  no_booking: "нет booking",
};

export function qtyOf(n: number | undefined): number {
  if (!Number.isFinite(n) || !n || n < 1) return 1;
  return Math.min(20, Math.floor(n));
}

export function requestsForRole(requests: EventRequestLite[], requirementId?: string): EventRequestLite[] {
  if (!requirementId) return [];
  return requests.filter((item) => item.requirement_id === requirementId);
}

export function isClosedRequest(item: EventRequestLite): boolean {
  return Boolean(item.booking_id) || item.status === "Confirmed";
}

export function isCancelledRequest(item: EventRequestLite): boolean {
  return item.status === "Cancelled" || item.status === "Declined" || item.status === "Expired";
}

export function cancelledRequestsForRole(
  requests: EventRequestLite[],
  requirementId?: string,
): EventRequestLite[] {
  return requestsForRole(requests, requirementId).filter(isCancelledRequest);
}

export function needsReplacement(step: NextStepRole): boolean {
  return step.openSlots > 0 && step.openRequests.some(isCancelledRequest);
}

export function roleBlocker(requests: EventRequestLite[], need: number): RoleBlocker {
  const closed = requests.filter(isClosedRequest).length;
  const openSlots = Math.max(0, need - closed);
  const openRequests = requests.filter((item) => !isClosedRequest(item));
  if (openRequests.length < openSlots) return "no_request";
  if (openRequests.some((item) => !item.quote_id)) return "no_offer";
  return "no_booking";
}

export type NextStepRole = {
  requirement: RequirementLite;
  label: string;
  need: number;
  filled: number;
  openSlots: number;
  blocker: RoleBlocker;
  openRequests: EventRequestLite[];
};

export function buildNextSteps(
  requirements: RequirementLite[],
  requests: EventRequestLite[],
  labelFor: (req: RequirementLite) => string,
): NextStepRole[] {
  const steps: NextStepRole[] = [];
  for (const req of requirements) {
    const need = qtyOf(req.qty);
    const roleRequests = requestsForRole(requests, req.id);
    const filled = roleRequests.filter(isClosedRequest).length;
    const openSlots = Math.max(0, need - filled);
    if (openSlots === 0) continue;
    steps.push({
      requirement: req,
      label: labelFor(req),
      need,
      filled,
      openSlots,
      blocker: roleBlocker(roleRequests, need),
      openRequests: roleRequests.filter((item) => !isClosedRequest(item)),
    });
  }
  return steps;
}

export function unmatchedRequests<T extends EventRequestLite>(
  requests: T[],
  requirements: RequirementLite[],
): T[] {
  const ids = new Set(requirements.map((r) => r.id).filter((id): id is string => Boolean(id)));
  return requests.filter((item) => !item.requirement_id || !ids.has(item.requirement_id));
}

export function openLooseRequests<T extends EventRequestLite>(
  requests: T[],
  requirements: RequirementLite[],
): T[] {
  return unmatchedRequests(requests, requirements).filter((item) => !isClosedRequest(item));
}
