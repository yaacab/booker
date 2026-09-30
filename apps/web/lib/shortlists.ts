import { apiBase, ApiError } from "./api";
export type Reaction = "vote" | "favorite" | "reject" | null;
export const REACTIONS = { vote: "Голосую за", favorite: "❤️ Нравится", reject: "Не подходит" };
export type SharedItem = { target_id: string; name: string; city: string; summary: string; profile_path: string; counts: Record<Exclude<Reaction, null>, number>; feedback: { name: string; reaction: Reaction; comment: string }[]; mine: { reaction: Reaction; comment: string; revision: number } };
export type Shared = { title: string; target_type: "artist" | "venue"; expires_at: string; collaborative: boolean; guest_name: string | null; items: SharedItem[]; note: string };
export type ManagedShare = Shared & { id: string; event_id: string | null; active: boolean; can_manage: boolean; share_path?: string };
/** Guest capabilities never travel as account Authorization or active-organization headers. */
export async function guestApi<T>(token: string, path = "", secret = "", init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers); headers.set("Content-Type", "application/json"); if (secret) headers.set("X-Shortlist-Guest", secret);
  const response = await fetch(`${apiBase()}/shared/${encodeURIComponent(token)}${path}`, { ...init, headers, credentials: "omit", cache: "no-store", referrerPolicy: "no-referrer" });
  const data = await response.json();
  if (!response.ok) throw new ApiError(typeof data.detail === "string" ? data.detail : "Проверьте поля. Не добавляйте контакты и внешние ссылки.", response.status);
  return data as T;
}
