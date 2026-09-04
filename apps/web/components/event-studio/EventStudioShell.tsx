"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { getToken, trackClientEvent } from "@/lib/api";
import { moscowToday } from "@/lib/format";
import { loginHref } from "@/lib/next";
import {
  budgetHintFromSelection,
  loadCatalog,
  loadStoredDraft,
  mapCatalogTalent,
  mapCatalogVenue,
  newSubmitIdempotencyKey,
  saveStoredDraft,
  submitEventStudioDraft,
} from "./adapter";
import EventStudioMap from "./EventStudioMap";
import type { EventStudioDraft, SaveStatus, TalentItem, VenueItem } from "./types";
import { EMPTY_DRAFT } from "./types";

const AUTOSAVE_MS = 750;
const CATALOG_DEBOUNCE_MS = 400;

export default function EventStudioShell() {
  const router = useRouter();
  const [draft, setDraft] = useState<EventStudioDraft>(EMPTY_DRAFT);
  const [hydrated, setHydrated] = useState(false);
  const [talents, setTalents] = useState<TalentItem[]>([]);
  const [venues, setVenues] = useState<VenueItem[]>([]);
  const [loadingTalents, setLoadingTalents] = useState(false);
  const [talentsError, setTalentsError] = useState<string | null>(null);
  const [saveStatus, setSaveStatus] = useState<SaveStatus>("saved");
  const [submitting, setSubmitting] = useState(false);
  const [submitError, setSubmitError] = useState<string | null>(null);
  const [online, setOnline] = useState(true);
  const idempotencyRef = useRef(newSubmitIdempotencyKey());
  const catalogAbortRef = useRef<AbortController | null>(null);

  useEffect(() => {
    const stored = loadStoredDraft();
    if (stored) setDraft(stored.draft);
    setHydrated(true);
    trackClientEvent("event.studio.started");
  }, []);

  useEffect(() => {
    const sync = () => setOnline(navigator.onLine);
    sync();
    window.addEventListener("online", sync);
    window.addEventListener("offline", sync);
    return () => {
      window.removeEventListener("online", sync);
      window.removeEventListener("offline", sync);
    };
  }, []);

  useEffect(() => {
    if (!hydrated) return;
    setSaveStatus(online ? "saving" : "offline");
    const timer = window.setTimeout(() => {
      try {
        saveStoredDraft(draft);
        setSaveStatus(online ? "saved" : "offline");
      } catch {
        setSaveStatus("error");
      }
    }, AUTOSAVE_MS);
    return () => window.clearTimeout(timer);
  }, [draft, hydrated, online]);

  const reloadCatalog = useCallback(async () => {
    catalogAbortRef.current?.abort();
    const controller = new AbortController();
    catalogAbortRef.current = controller;
    setLoadingTalents(true);
    setTalentsError(null);
    try {
      const data = await loadCatalog(draft.city || "Москва", draft.date, undefined, controller.signal);
      if (catalogAbortRef.current !== controller) return;
      setTalents(data.items.map((item) => mapCatalogTalent(item, draft.date)));
      setVenues(data.venues.map(mapCatalogVenue));
    } catch (err) {
      if (catalogAbortRef.current !== controller) return;
      setTalentsError(err instanceof Error ? err.message : "Каталог недоступен");
      setTalents([]);
      setVenues([]);
    } finally {
      if (catalogAbortRef.current === controller) setLoadingTalents(false);
    }
  }, [draft.city, draft.date]);

  // Город набирается вручную — не дёргаем /catalog/search на каждый символ.
  useEffect(() => {
    if (!hydrated) return;
    const timer = window.setTimeout(() => void reloadCatalog(), CATALOG_DEBOUNCE_MS);
    return () => window.clearTimeout(timer);
  }, [hydrated, reloadCatalog]);

  const budgetHint = useMemo(() => budgetHintFromSelection(talents, venues, draft), [talents, venues, draft]);

  async function handleContinue() {
    if (!getToken()) {
      router.push(loginHref("/events/new?event_studio_map_v1=1"));
      return;
    }
    if (!draft.title.trim()) {
      setSubmitError("Укажите название события.");
      return;
    }
    if (draft.date && draft.date.slice(0, 10) < moscowToday()) {
      setSubmitError("Выберите текущую или будущую дату.");
      return;
    }
    setSubmitting(true);
    setSubmitError(null);
    try {
      const { eventId, reused } = await submitEventStudioDraft(draft, talents, idempotencyRef.current);
      if (reused) {
        setSubmitError("Заявка уже отправлена — открываем событие.");
      }
      router.push(`/events/${eventId}`);
    } catch (err) {
      setSubmitError(err instanceof Error ? err.message : "Не удалось отправить");
    } finally {
      setSubmitting(false);
    }
  }

  if (!hydrated) {
    return (
      <main className="event-studio-shell">
        <p className="kicker">Event Studio Map</p>
        <h1 className="event-studio-loading-title">Загрузка карты события</h1>
        <div className="skeleton" style={{ minHeight: 240 }} />
      </main>
    );
  }

  return (
    <EventStudioMap
      draft={draft}
      onDraftChange={setDraft}
      talents={talents}
      venues={venues}
      budgetHint={budgetHint}
      loadingTalents={loadingTalents}
      talentsError={talentsError}
      saveStatus={saveStatus}
      onRetrySave={() => {
        try {
          saveStoredDraft(draft);
          setSaveStatus(online ? "saved" : "offline");
        } catch {
          setSaveStatus("error");
        }
      }}
      onReloadCatalog={() => void reloadCatalog()}
      onContinue={() => void handleContinue()}
      submitting={submitting}
      submitError={submitError}
      legacyLink={<Link href="/events/new">Классический мастер</Link>}
    />
  );
}
