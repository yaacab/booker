"use client";

import { useRouter } from "next/navigation";
import { useCallback, useEffect, useMemo, useState } from "react";
import { api, getActiveOrg, getToken, setActiveOrg, trackClientEvent } from "@/lib/api";
import { cabinetPathForKind } from "@/lib/cabinetRoutes";
import type { CustomerBooking, CustomerDealRoom, CustomerEvent } from "./types";

const DEAL_ROOM_STATUSES = new Set(["Negotiation", "DateHeld", "AwaitingContract", "AwaitingPayment"]);

export function useCustomerCabinetData() {
  const router = useRouter();
  const [ready, setReady] = useState(false);
  const [error, setError] = useState("");
  const [email, setEmail] = useState("");
  const [orgName, setOrgName] = useState("");
  const [events, setEvents] = useState<CustomerEvent[]>([]);
  const [dealRooms, setDealRooms] = useState<CustomerDealRoom[]>([]);

  const load = useCallback(async () => {
    if (!getToken()) {
      setError("Нужен вход");
      setReady(true);
      return;
    }
    try {
      const me = await api<{
        email: string;
        organizations?: { id: string; name: string; kind: string }[];
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
      if (org.kind !== "customer") {
        router.replace(cabinetPathForKind(org.kind));
        return;
      }
      setActiveOrg(org.id);
      setOrgName(org.name);
      const q = `?organization_id=${encodeURIComponent(org.id)}`;
      const [ev, bk] = await Promise.all([
        api<{ items: CustomerEvent[] }>(`/events${q}`),
        api<{ items: CustomerBooking[] }>(`/bookings${q}`),
      ]);
      setEvents(ev.items);
      const activeBookings = bk.items.filter((b) => DEAL_ROOM_STATUSES.has(b.status));
      const rooms = await Promise.all(
        activeBookings.map((b) =>
          api<CustomerDealRoom>(`/deal-room/${b.id}`).catch(() => null),
        ),
      );
      setDealRooms(rooms.filter((r): r is CustomerDealRoom => r != null));
      trackClientEvent("cabinet.viewed", { kind: "customer" });
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

  const upcomingEvents = useMemo(
    () =>
      events
        .filter(
          (e) =>
            e.status !== "Draft" &&
            e.status !== "Cancelled" &&
            new Date(e.event_date).getTime() >= now - 86_400_000,
        )
        .sort((a, b) => new Date(a.event_date).getTime() - new Date(b.event_date).getTime())
        .slice(0, 6),
    [events, now],
  );

  const drafts = useMemo(
    () => events.filter((e) => e.status === "Draft").sort((a, b) => b.title.localeCompare(a.title, "ru")),
    [events],
  );

  const newOffers = useMemo(
    () =>
      dealRooms.filter(
        (d) => d.status === "Negotiation" && d.quote.supplier_ack && !d.quote.customer_ack,
      ),
    [dealRooms],
  );

  const expiringHolds = useMemo(
    () =>
      dealRooms
        .filter((d) => d.hold?.status === "active" && d.hold.expires_at)
        .sort(
          (a, b) =>
            new Date(a.hold!.expires_at).getTime() - new Date(b.hold!.expires_at).getTime(),
        ),
    [dealRooms],
  );

  const empty =
    ready &&
    !error &&
    upcomingEvents.length === 0 &&
    drafts.length === 0 &&
    newOffers.length === 0 &&
    expiringHolds.length === 0;

  return {
    ready,
    error,
    email,
    orgName,
    upcomingEvents,
    drafts,
    newOffers,
    expiringHolds,
    empty,
    reload: load,
  };
}
