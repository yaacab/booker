"use client";

import { useRouter } from "next/navigation";
import { useCallback, useEffect, useMemo, useState } from "react";
import { api, getActiveOrg, getToken, setActiveOrg, trackClientEvent } from "@/lib/api";
import { cabinetPathForKind } from "@/lib/cabinetRoutes";
import type {
  CalendarConflict,
  PerformerBooking,
  PerformerDealRoom,
  PerformerRequest,
  ProfileCompleteness,
} from "./types";

const ACTIVE_DEAL_STATUSES = new Set(["Negotiation", "DateHeld", "AwaitingContract", "AwaitingPayment"]);
const UPCOMING_STATUSES = new Set(["Confirmed", "InProgress", "DateHeld", "AwaitingPayment", "AwaitingContract"]);
const CONFLICT_STATUSES = new Set(["Confirmed", "InProgress", "DateHeld"]);
const HOLD_SOON_MS = 48 * 3600_000;
const CONFLICT_WINDOW_MS = 4 * 3600_000;

export function usePerformerCabinetData() {
  const router = useRouter();
  const [ready, setReady] = useState(false);
  const [error, setError] = useState("");
  const [email, setEmail] = useState("");
  const [orgName, setOrgName] = useState("");
  const [orgId, setOrgId] = useState("");
  const [role, setRole] = useState("");
  const [requests, setRequests] = useState<PerformerRequest[]>([]);
  const [bookings, setBookings] = useState<PerformerBooking[]>([]);
  const [dealRooms, setDealRooms] = useState<PerformerDealRoom[]>([]);
  const [completeness, setCompleteness] = useState<ProfileCompleteness | null>(null);
  const [offerBusy, setOfferBusy] = useState<string | null>(null);

  const load = useCallback(async () => {
    if (!getToken()) {
      setError("Нужен вход");
      setReady(true);
      return;
    }
    try {
      const me = await api<{
        email: string;
        organizations?: { id: string; name: string; kind: string; role?: string }[];
        active_organization_id?: string;
      }>("/me");
      setEmail(me.email);
      const activeOrgId = getActiveOrg() || me.active_organization_id || me.organizations?.[0]?.id;
      const org = me.organizations?.find((o) => o.id === activeOrgId) || me.organizations?.[0];
      if (!org) {
        setError("Нет организации");
        setReady(true);
        return;
      }
      if (org.kind !== "artist") {
        router.replace(cabinetPathForKind(org.kind));
        return;
      }
      setActiveOrg(org.id);
      setOrgId(org.id);
      setOrgName(org.name);
      setRole(org.role || "");
      const q = `?organization_id=${encodeURIComponent(org.id)}`;
      const [rq, bk, comp] = await Promise.all([
        api<{ items: PerformerRequest[] }>(`/requests${q}`),
        api<{ items: PerformerBooking[] }>(`/bookings${q}`),
        api<ProfileCompleteness>(`/organizations/${encodeURIComponent(org.id)}/supply-completeness`),
      ]);
      setRequests(rq.items);
      setBookings(bk.items);
      setCompleteness(comp);
      const activeBookings = bk.items.filter((b) => ACTIVE_DEAL_STATUSES.has(b.status));
      const rooms = await Promise.all(
        activeBookings.map((b) =>
          api<PerformerDealRoom>(`/deal-room/${b.id}`).catch(() => null),
        ),
      );
      setDealRooms(rooms.filter((r): r is PerformerDealRoom => r != null));
      trackClientEvent("cabinet.viewed", { kind: "performer" });
      setError("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Ошибка");
    } finally {
      setReady(true);
    }
  }, [router]);

  useEffect(() => {
    void load();
  }, [load]);

  const now = Date.now();

  const newRequests = useMemo(
    () =>
      requests
        .filter((r) => !r.offer_id && !r.booking_id)
        .sort((a, b) => (b.event_date || "").localeCompare(a.event_date || "")),
    [requests],
  );

  const awaitingResponse = useMemo(
    () =>
      dealRooms.filter(
        (d) => d.status === "Negotiation" && d.quote.supplier_ack && !d.quote.customer_ack,
      ),
    [dealRooms],
  );

  const expiringOffers = useMemo(
    () =>
      dealRooms
        .filter(
          (d) =>
            d.hold?.status === "active" &&
            d.hold.expires_at &&
            new Date(d.hold.expires_at).getTime() - now <= HOLD_SOON_MS,
        )
        .sort(
          (a, b) =>
            new Date(a.hold!.expires_at).getTime() - new Date(b.hold!.expires_at).getTime(),
        ),
    [dealRooms, now],
  );

  const activeHolds = useMemo(
    () =>
      dealRooms
        .filter((d) => d.hold?.status === "active" && d.hold.expires_at)
        .sort(
          (a, b) =>
            new Date(a.hold!.expires_at).getTime() - new Date(b.hold!.expires_at).getTime(),
        ),
    [dealRooms],
  );

  const upcomingPerformances = useMemo(
    () =>
      bookings
        .filter(
          (b) =>
            b.event_date &&
            UPCOMING_STATUSES.has(b.status) &&
            new Date(b.event_date).getTime() >= now - 86_400_000,
        )
        .sort((a, b) => new Date(a.event_date!).getTime() - new Date(b.event_date!).getTime())
        .slice(0, 6),
    [bookings, now],
  );

  const calendarConflicts = useMemo(() => {
    const active = bookings.filter(
      (b) => b.event_date && CONFLICT_STATUSES.has(b.status),
    );
    const out: CalendarConflict[] = [];
    for (let i = 0; i < active.length; i++) {
      for (let j = i + 1; j < active.length; j++) {
        const aTime = new Date(active[i].event_date!).getTime();
        const bTime = new Date(active[j].event_date!).getTime();
        if (Math.abs(aTime - bTime) < CONFLICT_WINDOW_MS) {
          out.push({
            booking_id: active[i].id,
            event_title: active[i].event_title,
            event_date: active[i].event_date!,
            conflict_with: active[j].event_title,
            conflict_booking_id: active[j].id,
          });
        }
      }
    }
    return out;
  }, [bookings]);

  const profileIncomplete =
    completeness?.applicable && completeness.score < 100 ? completeness : null;

  const empty =
    ready &&
    !error &&
    newRequests.length === 0 &&
    awaitingResponse.length === 0 &&
    expiringOffers.length === 0 &&
    activeHolds.length === 0 &&
    upcomingPerformances.length === 0 &&
    calendarConflicts.length === 0 &&
    !profileIncomplete;

  async function sendOffer(item: PerformerRequest) {
    if (!item.slot_id) {
      setError("Нет свободного слота для оффера");
      return;
    }
    setOfferBusy(item.id);
    try {
      const res = await api<{ booking_id: string }>(`/requests/${item.id}/offers`, {
        method: "POST",
        body: JSON.stringify({ honorarium_rub: item.honorarium_rub, slot_id: item.slot_id }),
      });
      trackClientEvent("cabinet.offer_sent", { request_id: item.id });
      window.location.href = `/deals/${res.booking_id}`;
    } catch (err) {
      setError(err instanceof Error ? err.message : "Не удалось ответить");
    } finally {
      setOfferBusy(null);
    }
  }

  return {
    ready,
    error,
    email,
    orgName,
    orgId,
    role,
    newRequests,
    awaitingResponse,
    expiringOffers,
    activeHolds,
    upcomingPerformances,
    calendarConflicts,
    profileIncomplete,
    empty,
    offerBusy,
    sendOffer,
    reload: load,
  };
}
