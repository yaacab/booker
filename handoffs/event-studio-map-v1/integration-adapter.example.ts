import type { EventStudioDraft } from "./EventStudioMap";

// Replace these stubs with the project's existing API client. The visual layer
// intentionally owns no price, commission, hold, payment or refund calculation.
export async function saveEventDraft(draft: EventStudioDraft) {
  return fetch("/api/events/draft", {
    method: "PUT",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(draft),
  });
}

export async function requestServerQuotes(eventId: string) {
  return fetch(`/api/events/${eventId}/requests`, { method: "POST" });
}

export async function loadAvailability(input: { city: string; date: string; role?: string }) {
  const query = new URLSearchParams(input).toString();
  return fetch(`/api/catalog/availability?${query}`).then((response) => response.json());
}
