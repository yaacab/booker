"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { api } from "@/lib/api";
import { parseBookerDate } from "@/lib/format";
import type { PerformerBooking, PerformerVacationItem } from "./types";

type CalendarSlot = { id: string; status: string; starts_at: string; ends_at: string };

export function usePerformerCalendarOverview(orgId: string, artistId: string, bookings: PerformerBooking[]) {
  const [slots, setSlots] = useState<CalendarSlot[]>([]);
  const [vacation, setVacation] = useState<PerformerVacationItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState("");

  const reload = useCallback(async () => {
    if (!orgId) return;
    setLoading(true);
    try {
      const [calendarResult, vacationResult] = await Promise.allSettled([
        artistId ? api<{ slots: CalendarSlot[] }>(`/artists/${encodeURIComponent(artistId)}`) : Promise.resolve({ slots: [] }),
        api<{ items: PerformerVacationItem[] }>(`/organizations/${encodeURIComponent(orgId)}/vacation`),
      ]);
      setVacation(vacationResult.status === "fulfilled" ? vacationResult.value.items : []);
      if (calendarResult.status === "rejected") throw calendarResult.reason;
      setSlots(calendarResult.value.slots || []);
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
        .filter((s) => s.status === "open" && parseBookerDate(s.starts_at).getTime() >= now)
        .sort((a, b) => parseBookerDate(a.starts_at).getTime() - parseBookerDate(b.starts_at).getTime()),
    [slots, now],
  );

  const busySlots = useMemo(
    () =>
      slots
        .filter((s) => !["open", "cancelled"].includes(s.status) && parseBookerDate(s.starts_at).getTime() >= now - 86_400_000)
        .sort((a, b) => parseBookerDate(a.starts_at).getTime() - parseBookerDate(b.starts_at).getTime())
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
          parseBookerDate(b.event_date).getTime() >= now - 86_400_000,
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
