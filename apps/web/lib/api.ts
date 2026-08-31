const TOKEN_KEY = "booker.token";
const ORG_KEY = "booker.org";

export function apiBase(): string {
  if (typeof window !== "undefined") {
    return process.env.NEXT_PUBLIC_API_URL || "/api";
  }
  return (
    process.env.BOOKER_INTERNAL_API_URL ||
    process.env.NEXT_PUBLIC_API_URL ||
    "http://127.0.0.1:8000"
  );
}

export function getToken(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem(TOKEN_KEY);
}

export function getActiveOrg(): string | null {
  if (typeof window === "undefined") return null;
  return localStorage.getItem(ORG_KEY);
}

export function setActiveOrg(id: string | null): void {
  if (typeof window === "undefined") return;
  if (id) localStorage.setItem(ORG_KEY, id);
  else localStorage.removeItem(ORG_KEY);
}

export function setToken(token: string | null): void {
  if (typeof window === "undefined") return;
  if (token) localStorage.setItem(TOKEN_KEY, token);
  else {
    localStorage.removeItem(TOKEN_KEY);
    localStorage.removeItem(ORG_KEY);
  }
}

export class ApiError extends Error {
  status: number;

  constructor(message: string, status: number) {
    super(message);
    this.status = status;
  }
}

export function isWriteRole(role?: string | null): boolean {
  return role === "owner" || role === "admin" || role === "manager";
}

export async function api<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  headers.set("Content-Type", "application/json");
  const token = getToken();
  if (token) headers.set("Authorization", `Bearer ${token}`);
  const org = getActiveOrg();
  if (org) headers.set("X-Booker-Org", org);
  const res = await fetch(`${apiBase()}${path}`, { ...init, headers });
  const text = await res.text();
  let data: { detail?: unknown } = {};
  try {
    data = text ? JSON.parse(text) : {};
  } catch {
    data = { detail: text };
  }
  if (!res.ok) {
    const detail = data.detail;
    const message = typeof detail === "string" ? detail : text || res.statusText;
    throw new ApiError(message, res.status);
  }
  return data as T;
}

type OrgCreateBody = {
  name: string;
  kind: string;
  city?: string;
  confirm_another_workspace?: boolean;
};

export async function createOrg(body: OrgCreateBody): Promise<{ id: string }> {
  return api("/orgs", { method: "POST", body: JSON.stringify(body) });
}

export async function createOrgWithConfirm(
  body: Omit<OrgCreateBody, "confirm_another_workspace">,
  confirm: (message: string) => boolean = (message) => window.confirm(message),
): Promise<{ id: string }> {
  try {
    return await createOrg(body);
  } catch (err) {
    if (err instanceof ApiError && err.status === 409 && confirm(err.message)) {
      return createOrg({ ...body, confirm_another_workspace: true });
    }
    throw err;
  }
}
