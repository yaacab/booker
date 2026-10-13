"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import { api, getActiveOrg, getToken, SESSION_CHANGED_EVENT } from "@/lib/api";
import { formatWhen, money } from "@/lib/format";

type Kind = "artist" | "venue";
type Preview = {
  id: string;
  name: string;
  city: string;
  category?: string;
  capacity?: number;
  address?: string;
  description?: string;
  rider?: Record<string, string>;
  tariffs?: { id: string; title: string; honorarium_rub: number }[];
  slots?: { id: string; starts_at: string; ends_at?: string; status: string; hall?: string }[];
};
type PreviewState = { status: "loading" | "denied" | "ready"; kind?: Kind; generation?: number; profile?: Preview };

export function CabinetProfilePreview() {
  const params = useParams<{ kind: string; id: string }>();
  const kind: Kind | null = params.kind === "artist" || params.kind === "venue" ? params.kind : null;
  const id = params.id;
  const [state, setState] = useState<PreviewState>({ status: "loading" });
  const [sessionVersion, setSessionVersion] = useState(0);
  const sessionGeneration = useRef(0);

  useEffect(() => {
    let current = true;
    const capturedGeneration = sessionGeneration.current;
    const token = getToken();
    const orgId = getActiveOrg();
    setState({ status: "loading" });

    const sameSession = () =>
      current && sessionGeneration.current === capturedGeneration && getToken() === token && getActiveOrg() === orgId;
    const invalidate = () => {
      sessionGeneration.current += 1;
      setState({ status: "denied" });
      setSessionVersion((version) => version + 1);
    };
    const clearOnChange = () => {
      if (getToken() !== token || getActiveOrg() !== orgId) invalidate();
    };
    window.addEventListener(SESSION_CHANGED_EVENT, invalidate);
    window.addEventListener("storage", clearOnChange);
    window.addEventListener("focus", clearOnChange);
    const unsubscribe = () => {
      current = false;
      window.removeEventListener(SESSION_CHANGED_EVENT, invalidate);
      window.removeEventListener("storage", clearOnChange);
      window.removeEventListener("focus", clearOnChange);
    };

    if (!kind || !id || !token || !orgId) {
      setState({ status: "denied" });
      return unsubscribe;
    }
    const selectedOrgId = orgId;
    const selectedKind = kind;

    async function load() {
      try {
        const me = await api<{ organizations?: { id: string; kind: string }[] }>("/me", { cache: "no-store" });
        if (!sameSession()) return;
        if (!me.organizations?.some((org) => org.id === orgId && org.kind === kind)) {
          setState({ status: "denied" });
          return;
        }
        const targets = await api<{ items: { resource_type: string; resource_id: string; venue_id?: string }[] }>(
          `/organizations/${encodeURIComponent(selectedOrgId)}/calendar-targets`,
          { cache: "no-store" },
        );
        if (!sameSession()) return;
        const belongsToOrg = targets.items.some((target) =>
          kind === "artist"
            ? target.resource_type === "artist" && target.resource_id === id
            : target.venue_id === id || (target.resource_type === "venue" && target.resource_id === id),
        );
        if (!belongsToOrg) {
          setState({ status: "denied" });
          return;
        }
        const resource = kind === "artist" ? "artists" : "venues";
        const profile = await api<Preview>(`/${resource}/${encodeURIComponent(id)}`, { cache: "no-store" });
        if (sameSession() && profile.id === id) {
          setState({ status: "ready", kind: selectedKind, generation: capturedGeneration, profile });
        }
        else if (sameSession()) setState({ status: "denied" });
      } catch {
        if (sameSession()) setState({ status: "denied" });
      }
    }

    void load();
    return unsubscribe;
  }, [kind, id, sessionVersion]);

  const back = kind === "venue" ? "/cabinet/venue/halls" : "/cabinet/performer/services";
  const profile = state.status === "ready" && state.kind === kind &&
    state.generation === sessionGeneration.current && state.profile?.id === id
    ? state.profile
    : undefined;

  return (
    <main className="cabinet-v2" data-testid="cabinet-profile-preview">
      <header className="cabinet-hero">
        <div className="cabinet-hero-copy">
          <p className="cabinet-eyebrow">Предпросмотр · только для участников организации</p>
          <h1>{profile?.name || "Предпросмотр профиля"}</h1>
          <p className="cabinet-lede">Черновик профиля. Публичная витрина появится после публикации.</p>
          <Link className="btn secondary" href={back}>← Вернуться в кабинет</Link>
        </div>
      </header>
      {state.status === "loading" ? <p role="status">Загружаем предпросмотр…</p> : null}
      {state.status === "denied" ? <p role="alert">Профиль недоступен. Войдите в нужную организацию и откройте ссылку из кабинета.</p> : null}
      {profile ? (
        <section className="card" aria-label="Профиль">
          <p>{profile.city}{profile.category ? ` · ${profile.category}` : ""}</p>
          {profile.address ? <p>Адрес: {profile.address}</p> : null}
          {profile.capacity ? <p>Вместимость: {profile.capacity}</p> : null}
          {profile.description ? <p>{profile.description}</p> : null}
          {profile.rider && Object.values(profile.rider).some(Boolean) ? (
            <section id="rider"><h2>Райдер</h2><ul>{Object.entries(profile.rider).filter(([, value]) => value).map(([key, value]) => <li key={key}>{key}: {value}</li>)}</ul></section>
          ) : null}
          {profile.tariffs?.length ? <section><h2>Тарифы</h2><ul>{profile.tariffs.map((tariff) => <li key={tariff.id}>{tariff.title} · {money(tariff.honorarium_rub)}</li>)}</ul></section> : null}
          {profile.slots?.length ? <section><h2>Календарь</h2><ul>{profile.slots.map((slot) => <li key={slot.id}>{formatWhen(slot.starts_at)} · {slot.status}{slot.hall ? ` · ${slot.hall}` : ""}</li>)}</ul></section> : null}
        </section>
      ) : null}
    </main>
  );
}
