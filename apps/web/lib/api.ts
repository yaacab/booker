const TOKEN_KEY = "booker.token";
const ORG_KEY = "booker.org";

export function apiBase(): string {
  if (typeof window !== "undefined") {
    if (sessionStorage.getItem("booker.demo.token")) return "/development-api";
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
  return sessionStorage.getItem("booker.demo.token") || localStorage.getItem(TOKEN_KEY);
}

export function getActiveOrg(): string | null {
  if (typeof window === "undefined") return null;
  if (sessionStorage.getItem("booker.demo.token")) return sessionStorage.getItem("booker.demo.org");
  return localStorage.getItem(ORG_KEY);
}

export function setActiveOrg(id: string | null): void {
  if (typeof window === "undefined") return;
  if (sessionStorage.getItem("booker.demo.token")) {
    if(id) sessionStorage.setItem("booker.demo.org",id); else sessionStorage.removeItem("booker.demo.org");
    return;
  }
  if (id) localStorage.setItem(ORG_KEY, id);
  else localStorage.removeItem(ORG_KEY);
}

export function setToken(token: string | null): void {
  if (typeof window === "undefined") return;
  if (sessionStorage.getItem("booker.demo.token")) {
    if(token)sessionStorage.setItem("booker.demo.token",token);
    else for(const key of ["booker.demo.token","booker.demo.org","booker.demo.admin"])sessionStorage.removeItem(key);
    return;
  }
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

/** Keep proxy HTML, exception bodies and validation input values out of product copy. */
export function apiErrorMessage(status: number, detail: unknown): string {
  if (status >= 500) return "Сервис временно недоступен. Попробуйте ещё раз позже.";
  if (typeof detail === "string" && detail.trim() && detail.length <= 500 && !/<[a-z!/]/i.test(detail)) return detail;
  if (Array.isArray(detail)) return "Проверьте заполненные поля и повторите отправку.";
  return "Не удалось выполнить запрос. Обновите страницу или попробуйте позже.";
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
  let data: unknown = {};
  try {
    data = text ? JSON.parse(text) : {};
  } catch {
    throw new ApiError(apiErrorMessage(res.status, undefined), res.status);
  }
  if (!res.ok) {
    const detail = data && typeof data === "object" && "detail" in data ? data.detail : undefined;
    const message = apiErrorMessage(res.status, detail);
    throw new ApiError(message, res.status);
  }
  return data as T;
}

export function trackClientEvent(
  name: string,
  properties?: Record<string, string | number | boolean | null>,
): void {
  if (typeof window === "undefined") return;
  const token = getToken();
  if (!token) return;
  const headers: Record<string, string> = {
    "Content-Type": "application/json",
    Authorization: `Bearer ${token}`,
  };
  const org = getActiveOrg();
  if (org) headers["X-Booker-Org"] = org;
  void fetch(`${apiBase()}/analytics/events`, {
    method: "POST",
    headers,
    body: JSON.stringify({ name, properties: properties ?? {} }),
    keepalive: true,
  }).catch(() => {});
}

/** @internal test hook */
export function clientEventFetchInit(
  body: string,
  headers: Record<string, string>,
): RequestInit {
  return {
    method: "POST",
    headers,
    body,
    keepalive: true,
  };
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
