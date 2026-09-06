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

export type NegotiationSeed = {
  customer: AuthSession & { orgId: string };
  owner: AuthSession & { orgId: string };
  artistId: string;
  slotId: string;
  requestId: string;
  offerId: string;
  bookingId: string;
  quoteId: string;
  honorariumRub: number;
  terms: string;
  eventTitle: string;
  startsAt: string;
  endsAt: string;
};

/** Customer + artist + slot + request + offer — готово к ack/hold (E08/E09). */
export async function seedNegotiation(
  request: APIRequestContext,
  opts?: { honorariumRub?: number; terms?: string; slotStartsAt?: string; slotEndsAt?: string },
): Promise<NegotiationSeed> {
  const suffix = `${Date.now()}-${Math.floor(Math.random() * 1e6)}`;
  const startsAt = opts?.slotStartsAt ?? "2026-10-12T18:00:00+00:00";
  const endsAt = opts?.slotEndsAt ?? "2026-10-12T22:00:00+00:00";
  const honorariumRub = opts?.honorariumRub ?? 100_000;
  const terms = opts?.terms ?? "E2E: 2 часа сет";
  const eventTitle = `E2E Deal ${suffix}`;

  const customer = await register(request, `e2e-deal-c-${suffix}@booker.test`, "E2E Deal Клиент");
  const owner = await register(request, `e2e-deal-a-${suffix}@booker.test`, "E2E Deal Артист");

  const custOrg = await postJson<{ id: string }>(request, "/orgs", customer.token, {
    name: "E2E Deal Заказчик",
    kind: "customer",
  });
  const artistOrg = await postJson<{ id: string }>(request, "/orgs", owner.token, {
    name: "E2E Deal Шоу",
    kind: "artist",
  });
  const artist = await postJson<{ id: string }>(request, "/artists", owner.token, {
    organization_id: artistOrg.id,
    name: `E2E Deal DJ ${suffix}`,
    category: "dj",
  });
  await postJson(request, `/artists/${artist.id}/tariffs`, owner.token, {
    title: "Сет",
    honorarium_rub: honorariumRub,
  });
  const slot = await postJson<{ id: string }>(request, "/slots", owner.token, {
    resource_type: "artist",
    resource_id: artist.id,
    starts_at: startsAt,
    ends_at: endsAt,
  });
  const event = await postJson<{ id: string }>(request, "/events", customer.token, {
    organization_id: custOrg.id,
    title: eventTitle,
    event_date: startsAt,
    guest_count: 80,
    budget_rub: 200_000,
  });
  const req = await postJson<{ id: string }>(request, `/events/${event.id}/requests`, customer.token, {
    resource_type: "artist",
    resource_id: artist.id,
  });
  const offer = await postJson<{
    id: string;
    booking_id: string;
    version: { id: string; quote_id: string; honorarium_rub: number; terms?: string };
  }>(request, `/requests/${req.id}/offers`, owner.token, {
    honorarium_rub: honorariumRub,
    slot_id: slot.id,
    terms,
  });

  return {
    customer: { ...customer, orgId: custOrg.id },
    owner: { ...owner, orgId: artistOrg.id },
    artistId: artist.id,
    slotId: slot.id,
    requestId: req.id,
    offerId: offer.id,
    bookingId: offer.booking_id,
    quoteId: offer.version.quote_id ?? offer.version.id,
    honorariumRub: offer.version.honorarium_rub,
    terms,
    eventTitle,
    startsAt,
    endsAt,
  };
}

export type HoldRaceSeed = NegotiationSeed & {
  customer2: AuthSession;
  bookingId2: string;
  offerId2: string;
};

/** Два бронирования на один слот (оба с двусторонним ack) — для E09 exclusivity. */
export async function seedSameSlotHoldRace(request: APIRequestContext): Promise<HoldRaceSeed> {
  const suffix = `${Date.now()}-${Math.floor(Math.random() * 1e6)}`;
  const startsAt = "2026-11-05T18:00:00+00:00";
  const endsAt = "2026-11-05T22:00:00+00:00";
  const ctx = await seedNegotiation(request, {
    honorariumRub: 100_000,
    terms: "E2E race A",
    slotStartsAt: startsAt,
    slotEndsAt: endsAt,
  });

  await postJson(request, `/offers/${ctx.offerId}/ack`, ctx.owner.token, { side: "supplier" }, ctx.owner.orgId);
  await postJson(request, `/offers/${ctx.offerId}/ack`, ctx.customer.token, { side: "customer" }, ctx.customer.orgId);

  const customer2 = await register(request, `e2e-deal-c2-${suffix}@booker.test`, "E2E Deal Клиент2");
  await postJson(
    request,
    `/orgs/${ctx.customer.orgId}/members`,
    ctx.customer.token,
    { user_id: customer2.user_id, role: "manager" },
    ctx.customer.orgId,
  );
  const event2 = await postJson<{ id: string }>(request, "/events", customer2.token, {
    organization_id: ctx.customer.orgId,
    title: `E2E Deal Race B ${suffix}`,
    event_date: startsAt,
    guest_count: 60,
    budget_rub: 150_000,
  }, ctx.customer.orgId);
  const req2 = await postJson<{ id: string }>(
    request,
    `/events/${event2.id}/requests`,
    customer2.token,
    { resource_type: "artist", resource_id: ctx.artistId },
    ctx.customer.orgId,
  );
  const offer2 = await postJson<{ id: string; booking_id: string }>(
    request,
    `/requests/${req2.id}/offers`,
    ctx.owner.token,
    { honorarium_rub: 95_000, slot_id: ctx.slotId, terms: "E2E race B" },
    ctx.owner.orgId,
  );
  await postJson(request, `/offers/${offer2.id}/ack`, ctx.owner.token, { side: "supplier" }, ctx.owner.orgId);
  await postJson(request, `/offers/${offer2.id}/ack`, customer2.token, { side: "customer" }, ctx.customer.orgId);

  return {
    ...ctx,
    customer2,
    bookingId2: offer2.booking_id,
    offerId2: offer2.id,
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

  let artistSlot: { id: string } | undefined;
  let venueSlot: { id: string } | undefined;
  let startsAt = "";
  let endsAt = "";
  for (let attempt = 0; attempt < 6; attempt++) {
    const dayOffset = 30 + ((Date.now() + attempt * 97_123) % 40);
    const slotStart = new Date(
      Date.now() + dayOffset * 86_400_000 + Math.floor(Math.random() * 3600_000 * 20) + attempt * 3 * 86_400_000,
    );
    slotStart.setUTCHours(10 + (slotStart.getUTCMinutes() % 8), (slotStart.getUTCSeconds() % 4) * 15, 0, 0);
    const slotEnd = new Date(slotStart.getTime() + 4 * 3600_000);
    startsAt = slotStart.toISOString();
    endsAt = slotEnd.toISOString();
    try {
      artistSlot = await postJson<{ id: string }>(request, "/slots", artist.token, {
        resource_type: "artist",
        resource_id: artistProfile.id,
        starts_at: startsAt,
        ends_at: endsAt,
      }, artistOrg.id);
      venueSlot = await postJson<{ id: string }>(request, "/slots", venueUser.token, {
        resource_type: "hall",
        resource_id: hallId,
        starts_at: startsAt,
        ends_at: endsAt,
      }, venueOrg.id);
      break;
    } catch (err) {
      const message = err instanceof Error ? err.message : String(err);
      if (!message.includes("(409)") || attempt === 5) throw err;
    }
  }
  if (!artistSlot || !venueSlot) {
    throw new Error("Failed to create cross-role slots after retries");
  }

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

export type OrgSwitchSeed = {
  user: AuthSession;
  customer: { orgId: string; orgName: string; eventTitle: string };
  artist: { orgId: string; orgName: string; eventTitle: string };
  venue: { orgId: string; orgName: string; eventTitle: string };
};

/**
 * Один пользователь в customer/artist/venue org — для E15 workspace switch.
 * У каждой роли свой уникальный event title, видимый только в её кабинете.
 */
export async function seedOrgSwitchWorkspace(request: APIRequestContext): Promise<OrgSwitchSeed> {
  const suffix = `${Date.now()}-${Math.floor(Math.random() * 1e6)}`;
  const user = await register(request, `e2e-e15-${suffix}@booker.test`, "E15 Multi");
  const peer = await register(request, `e2e-e15-peer-${suffix}@booker.test`, "E15 Peer");

  const customerOrgName = `E15 Cust Org ${suffix}`;
  const artistOrgName = `E15 Artist Org ${suffix}`;
  const venueOrgName = `E15 Venue Org ${suffix}`;
  const customerEventTitle = `E15-CUST-EVT-${suffix}`;
  const artistEventTitle = `E15-ARTIST-EVT-${suffix}`;
  const venueEventTitle = `E15-VENUE-EVT-${suffix}`;

  const customerOrg = await postJson<{ id: string }>(request, "/orgs", user.token, {
    name: customerOrgName,
    kind: "customer",
  });
  const artistOrg = await postJson<{ id: string }>(request, "/orgs", user.token, {
    name: artistOrgName,
    kind: "artist",
  });
  const venueOrg = await postJson<{ id: string }>(request, "/orgs", user.token, {
    name: venueOrgName,
    kind: "venue",
  });

  await postJson<{ id: string }>(
    request,
    "/events",
    user.token,
    {
      organization_id: customerOrg.id,
      title: customerEventTitle,
      event_date: "2026-12-20T18:00:00+00:00",
      guest_count: 40,
      budget_rub: 120_000,
      city: "Москва",
    },
    customerOrg.id,
  );

  const artist = await postJson<{ id: string }>(
    request,
    "/artists",
    user.token,
    {
      organization_id: artistOrg.id,
      name: `E15 DJ ${suffix}`,
      category: "dj",
    },
    artistOrg.id,
  );
  await postJson(
    request,
    `/artists/${artist.id}/tariffs`,
    user.token,
    { title: "Сет", honorarium_rub: 70_000 },
    artistOrg.id,
  );
  await postJson(
    request,
    "/slots",
    user.token,
    {
      resource_type: "artist",
      resource_id: artist.id,
      starts_at: "2026-12-21T18:00:00+00:00",
      ends_at: "2026-12-21T22:00:00+00:00",
    },
    artistOrg.id,
  );

  const venue = await postJson<{ id: string; hall_id: string }>(
    request,
    "/venues",
    user.token,
    {
      organization_id: venueOrg.id,
      name: `E15 Hall ${suffix}`,
      city: "Москва",
      capacity: 100,
    },
    venueOrg.id,
  );
  await postJson(
    request,
    "/slots",
    user.token,
    {
      resource_type: "hall",
      resource_id: venue.hall_id,
      starts_at: "2026-12-22T18:00:00+00:00",
      ends_at: "2026-12-22T22:00:00+00:00",
    },
    venueOrg.id,
  );

  const peerOrg = await postJson<{ id: string }>(request, "/orgs", peer.token, {
    name: `E15 Peer Cust ${suffix}`,
    kind: "customer",
  });

  const artistInbound = await postJson<{ id: string }>(
    request,
    "/events",
    peer.token,
    {
      organization_id: peerOrg.id,
      title: artistEventTitle,
      event_date: "2026-12-21T18:00:00+00:00",
      guest_count: 60,
      budget_rub: 150_000,
      city: "Москва",
    },
    peerOrg.id,
  );
  await postJson(
    request,
    `/events/${artistInbound.id}/requests`,
    peer.token,
    { resource_type: "artist", resource_id: artist.id },
    peerOrg.id,
  );

  const venueInbound = await postJson<{ id: string }>(
    request,
    "/events",
    peer.token,
    {
      organization_id: peerOrg.id,
      title: venueEventTitle,
      event_date: "2026-12-22T18:00:00+00:00",
      guest_count: 80,
      budget_rub: 200_000,
      city: "Москва",
    },
    peerOrg.id,
  );
  await postJson(
    request,
    `/events/${venueInbound.id}/requests`,
    peer.token,
    { resource_type: "venue", resource_id: venue.id },
    peerOrg.id,
  );

  return {
    user,
    customer: { orgId: customerOrg.id, orgName: customerOrgName, eventTitle: customerEventTitle },
    artist: { orgId: artistOrg.id, orgName: artistOrgName, eventTitle: artistEventTitle },
    venue: { orgId: venueOrg.id, orgName: venueOrgName, eventTitle: venueEventTitle },
  };
}

export { postJson, getJson };
