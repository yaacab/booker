import type { APIRequestContext, Page } from "@playwright/test";

export const API_BASE = process.env.BOOKER_API_URL ?? "http://127.0.0.1:8000";
const PASSWORD = "password1";

function authHeader(token: string): Record<string, string> {
  return { Authorization: `Bearer ${token}` };
}

async function postJson<T>(
  request: APIRequestContext,
  path: string,
  token: string,
  data: unknown,
): Promise<T> {
  const res = await request.post(`${API_BASE}${path}`, {
    headers: { ...authHeader(token), "Content-Type": "application/json" },
    data,
  });
  if (!res.ok()) {
    throw new Error(`${path} failed (${res.status()}): ${await res.text()}`);
  }
  return res.json() as Promise<T>;
}

export async function apiHealth(request: APIRequestContext): Promise<boolean> {
  const res = await request.get(`${API_BASE}/health`);
  return res.ok();
}

export async function register(
  request: APIRequestContext,
  email: string,
  name: string,
): Promise<{ token: string; user_id: string }> {
  const res = await request.post(`${API_BASE}/auth/register`, {
    headers: { "Content-Type": "application/json" },
    data: {
      email,
      password: PASSWORD,
      full_name: name,
      phone: "+79000000000",
      accept_offer: true,
      accept_privacy: true,
    },
  });
  if (!res.ok()) {
    throw new Error(`register failed (${res.status()}): ${await res.text()}`);
  }
  return res.json() as Promise<{ token: string; user_id: string }>;
}

export type RequestOfferSeed = {
  ownerToken: string;
  artistOrgId: string;
  eventTitle: string;
};

const EVENT_TITLE = "E2E Корпоратив";

/** Customer org + artist org, event, request — без оффера (для UI path). */
export async function seedRequestAwaitingOffer(request: APIRequestContext): Promise<RequestOfferSeed> {
  const suffix = Date.now();
  const customer = await register(request, `e2e-c-${suffix}@booker.test`, "E2E Клиент");
  const owner = await register(request, `e2e-a-${suffix}@booker.test`, "E2E Артист");

  const custOrg = await postJson<{ id: string }>(request, "/orgs", customer.token, {
    name: "E2E Заказчик",
    kind: "customer",
  });
  const artistOrg = await postJson<{ id: string }>(request, "/orgs", owner.token, {
    name: "E2E Шоу",
    kind: "artist",
  });
  const artist = await postJson<{ id: string }>(request, "/artists", owner.token, {
    organization_id: artistOrg.id,
    name: "E2E DJ",
    category: "dj",
  });
  await postJson(request, `/artists/${artist.id}/tariffs`, owner.token, {
    title: "Сет",
    honorarium_rub: 80000,
  });
  await postJson(request, "/slots", owner.token, {
    resource_type: "artist",
    resource_id: artist.id,
    starts_at: "2026-09-15T18:00:00+00:00",
    ends_at: "2026-09-15T22:00:00+00:00",
  });
  const event = await postJson<{ id: string }>(request, "/events", customer.token, {
    organization_id: custOrg.id,
    title: EVENT_TITLE,
    event_date: "2026-09-15T18:00:00+00:00",
    guest_count: 50,
    budget_rub: 150000,
  });
  await postJson(request, `/events/${event.id}/requests`, customer.token, {
    resource_type: "artist",
    resource_id: artist.id,
  });

  return {
    ownerToken: owner.token,
    artistOrgId: artistOrg.id,
    eventTitle: EVENT_TITLE,
  };
}

export async function injectSession(page: Page, token: string, orgId: string): Promise<void> {
  await page.addInitScript(
    ({ token, orgId }) => {
      localStorage.setItem("booker.token", token);
      localStorage.setItem("booker.org", orgId);
    },
    { token, orgId },
  );
}
