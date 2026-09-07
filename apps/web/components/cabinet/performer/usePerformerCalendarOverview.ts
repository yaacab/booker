"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { api } from "@/lib/api";
import type { PerformerBooking, PerformerVacationItem } from "./types";

type CalendarSlot = { id: string; status: string; starts_at: string; ends_at: string };

export function usePerformerCalendarOverview(orgId: string, artistId: string, bookings: PerformerBooking[]) {
  const [slots, setSlots] = useState<CalendarSlot[]>([]);
  const [vacation, setVacation] = useState<PerformerVacationItem[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState("");

  const reload = useCallback(async () => {
    if (!orgId) return;
    setLoading(true);
    try {
      const vacationRes = await api<{ items: PerformerVacationItem[] }>(
        `/organizations/${encodeURIComponent(orgId)}/vacation`,
      );
      setVacation(vacationRes.items);
      if (artistId) {
        const page = await api<{ slots: CalendarSlot[] }>(`/artists/${encodeURIComponent(artistId)}`);
        setSlots(page.slots || []);
      } else {
        setSlots([]);
      }
      setError("");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Не удалось загрузить календарь");
      setVacation([]);
      setSlots([]);
    } finally {
      setLoading(false);
    }
  }, [orgId, artistId]);

  useEffect(() => {
    void reload();
  }, [reload]);

  const now = Date.now();

  const openSlots = useMemo(
    () =>
      slots
        .filter((s) => s.status === "open" && new Date(s.starts_at).getTime() >= now)
        .sort((a, b) => new Date(a.starts_at).getTime() - new Date(b.starts_at).getTime()),
    [slots, now],
  );

  const busySlots = useMemo(
    () =>
      slots
        .filter((s) => s.status !== "open" && new Date(s.starts_at).getTime() >= now - 86_400_000)
        .sort((a, b) => new Date(a.starts_at).getTime() - new Date(b.starts_at).getTime())
        .slice(0, 6),
    [slots, now],
  );

  const activeVacation = useMemo(() => vacation.find((v) => v.active), [vacation]);

  const confirmedDates = useMemo(
    () =>
      bookings.filter(
        (b) =>
          b.event_date &&
          (b.status === "Confirmed" || b.status === "InProgress") &&
          new Date(b.event_date).getTime() >= now - 86_400_000,
      ).length,
    [bookings, now],
  );

  return {
    slots,
    openSlots,
    busySlots,
    activeVacation,
    confirmedDates,
    loading,
    error,
    reload,
  };
}
