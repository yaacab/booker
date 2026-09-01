import type { APIRequestContext, Page } from "@playwright/test";
import fs from "node:fs";
import path from "node:path";

export const API_BASE = process.env.BOOKER_API_URL ?? "http://127.0.0.1:8000";
export const DEMO_PASSWORD = "password1";
const TOKEN_CACHE = path.resolve(__dirname, ".demo-tokens.json");

export const DEMO_ACCOUNTS = {
  customer: "customer@booker.test",
  artist: "artist@booker.test",
  venue: "venue@booker.test",
} as const;

function authHeader(token: string, orgId?: string): Record<string, string> {
  const headers: Record<string, string> = { Authorization: `Bearer ${token}` };
  if (orgId) headers["X-Booker-Org"] = orgId;
  return headers;
}

async function postJson<T>(
  request: APIRequestContext,
  path: string,
  token: string,
  data: unknown,
  orgId?: string,
): Promise<T> {
  const res = await request.post(`${API_BASE}${path}`, {
    headers: { ...authHeader(token, orgId), "Content-Type": "application/json" },
    data,
  });
  if (!res.ok()) {
    throw new Error(`${path} failed (${res.status()}): ${await res.text()}`);
  }
  return res.json() as Promise<T>;
}

async function getJson<T>(
  request: APIRequestContext,
  path: string,
  token: string,
  orgId?: string,
): Promise<T> {
  const res = await request.get(`${API_BASE}${path}`, {
    headers: authHeader(token, orgId),
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
      password: DEMO_PASSWORD,
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

export type AuthSession = { token: string; user_id: string };

export type MeOrg = {
  id: string;
  name: string;
  kind: string;
  role?: string;
  can_confirm_offer?: boolean;
};

export async function login(request: APIRequestContext, email: string): Promise<AuthSession> {
  if (fs.existsSync(TOKEN_CACHE)) {
    const cached = JSON.parse(fs.readFileSync(TOKEN_CACHE, "utf8")) as Record<string, AuthSession>;
    if (cached[email]?.token) return cached[email];
  }
  for (let attempt = 0; attempt < 5; attempt++) {
    const res = await request.post(`${API_BASE}/auth/login`, {
      data: { email, password: DEMO_PASSWORD },
    });
    if (res.status() === 429 && attempt < 4) {
      await new Promise((r) => setTimeout(r, 2000 * (attempt + 1)));
      continue;
    }
    if (!res.ok()) {
      throw new Error(`login ${email} failed (${res.status()}): ${await res.text()}`);
    }
    return res.json() as Promise<AuthSession>;
  }
  throw new Error(`login ${email} exhausted retries`);
}

export async function fetchMe(
  request: APIRequestContext,
  token: string,
  orgId?: string,
): Promise<{ email: string; organizations: MeOrg[] }> {
  return getJson(request, "/me", token, orgId);
}

export type CrossRoleSeed = {
  eventTitle: string;
  eventId: string;
  eventDate: string;
  artistRequestId: string;
  venueRequestId: string;
  artistBookingId: string;
  venueBookingId: string;
  artistOfferId: string;
  venueOfferId: string;
  customer: AuthSession & { orgId: string };
  artist: AuthSession & { orgId: string };
  venue: AuthSession & { orgId: string };
  artistId: string;
  venueId: string;
  artistSlotId: string;
  venueSlotId: string;
};

/** Demo seed: событие с заявками на DJ Nova и Клуб Сигнал (без офферов). */
export async function seedCrossRoleEvent(request: APIRequestContext): Promise<CrossRoleSeed> {
  const customer = await login(request, DEMO_ACCOUNTS.customer);
  const artist = await login(request, DEMO_ACCOUNTS.artist);
  const venueUser = await login(request, DEMO_ACCOUNTS.venue);

  const customerMe = await fetchMe(request, customer.token);
  const artistMe = await fetchMe(request, artist.token);
  const venueMe = await fetchMe(request, venueUser.token);

  const custOrg = customerMe.organizations.find((o) => o.kind === "customer");
  const artistOrg = artistMe.organizations.find((o) => o.kind === "artist");
  const venueOrg = venueMe.organizations.find((o) => o.kind === "venue");
  if (!custOrg || !artistOrg || !venueOrg) {
    throw new Error("Demo seed incomplete: run `make seed` (customer/artist/venue orgs)");
  }

  const catalog = await getJson<{ items: { id: string; name: string }[] }>(
    request,
    "/catalog/search?city=Москва&category=dj",
    customer.token,
  );
  const dj = catalog.items.find((a) => a.name === "DJ Nova");
  if (!dj) throw new Error("DJ Nova not found in catalog — run make seed");

  const artistProfile = await getJson<{ id: string }>(request, `/artists/${dj.id}`, customer.token);

  const venueSearch = await getJson<{ venues: { id: string; name: string }[] }>(
    request,
    "/catalog/search?city=Москва&category=venue",
    customer.token,
  );
  const signal = venueSearch.venues.find((v) => v.name === "Клуб Сигнал");
  if (!signal) throw new Error("Клуб Сигнал not found — run make seed");

  const venueDetail = await getJson<{
    id: string;
    halls: { id: string }[];
  }>(request, `/venues/${signal.id}`, customer.token);
  const hallId = venueDetail.halls[0]?.id;
  if (!hallId) throw new Error("Venue has no halls");

  const unique = Date.now();
  const slotStart = new Date(unique + (30 + (unique % 40)) * 86_400_000);
  slotStart.setUTCHours(10 + (unique % 8), (unique % 4) * 15, 0, 0);
  const slotEnd = new Date(slotStart.getTime() + 4 * 3600_000);
  const startsAt = slotStart.toISOString();
  const endsAt = slotEnd.toISOString();

  const artistSlot = await postJson<{ id: string }>(request, "/slots", artist.token, {
    resource_type: "artist",
    resource_id: artistProfile.id,
    starts_at: startsAt,
    ends_at: endsAt,
  }, artistOrg.id);

  const venueSlot = await postJson<{ id: string }>(request, "/slots", venueUser.token, {
    resource_type: "hall",
    resource_id: hallId,
    starts_at: startsAt,
    ends_at: endsAt,
  }, venueOrg.id);

  const eventTitle = `E2E Cross-Role ${Date.now()}`;
  const event = await postJson<{
    id: string;
    requirements: { id: string; category_code: string }[];
  }>(
    request,
    "/events",
    customer.token,
    {
      organization_id: custOrg.id,
      title: eventTitle,
      event_date: startsAt,
      guest_count: 80,
      budget_rub: 500_000,
      requirements: [
        { category_code: "dj", qty: 1 },
        { category_code: "venue", qty: 1 },
      ],
    },
    custOrg.id,
  );

  const reqDj = await postJson<{ id: string }>(
    request,
    `/events/${event.id}/requests`,
    customer.token,
    {
      resource_type: "artist",
      resource_id: dj.id,
      requirement_id: event.requirements.find((r) => r.category_code === "dj")?.id,
    },
    custOrg.id,
  );
  const reqVenue = await postJson<{ id: string }>(
    request,
    `/events/${event.id}/requests`,
    customer.token,
    {
      resource_type: "venue",
      resource_id: signal.id,
      requirement_id: event.requirements.find((r) => r.category_code === "venue")?.id,
    },
    custOrg.id,
  );

  return {
    eventTitle,
    eventId: event.id,
    eventDate: startsAt,
    artistRequestId: reqDj.id,
    venueRequestId: reqVenue.id,
    artistBookingId: "",
    venueBookingId: "",
    artistOfferId: "",
    venueOfferId: "",
    customer: { ...customer, orgId: custOrg.id },
    artist: { ...artist, orgId: artistOrg.id },
    venue: { ...venueUser, orgId: venueOrg.id },
    artistId: dj.id,
    venueId: signal.id,
    artistSlotId: artistSlot.id,
    venueSlotId: venueSlot.id,
  };
}

export { postJson, getJson };
