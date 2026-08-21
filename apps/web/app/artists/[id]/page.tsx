"use client";

import { useEffect, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import { api, getToken } from "@/lib/api";
import { CHIP } from "@/lib/copy";
import { money, moscowDate } from "@/lib/format";
import { loginHref } from "@/lib/next";
import { SlotList } from "@/components/SlotList";

type Slot = { id: string; starts_at: string; ends_at: string; status: string };
type Artist = {
  id: string;
  name: string;
  city: string;
  category: string;
  verified?: boolean;
  media_url?: string | null;
  rider?: Record<string, string>;
  facts: { note: string; deals?: number; response?: string };
  tariffs: { id: string; title: string; honorarium_rub: number }[];
  slots: Slot[];
};

const CAT: Record<string, string> = { dj: "DJ-сет", host: "Ведущий", cover: "Кавер" };

export default function ArtistPage() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const [data, setData] = useState<Artist | null>(null);
  const [error, setError] = useState("");
  const [slotId, setSlotId] = useState("");
  const [busy, setBusy] = useState(false);
  const [wantedDay, setWantedDay] = useState<string | null>(null);

  useEffect(() => {
    const q = new URLSearchParams(window.location.search);
    const wanted = q.get("slot");
    const day = q.get("date");
    setWantedDay(day);
    fetch(`${process.env.NEXT_PUBLIC_API_URL || "/api"}/artists/${params.id}`)
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error("Не найден"))))
      .then((json: Artist) => {
        setData(json);
        const day = q.get("date");
        const live = json.slots.filter(
          (s) => !s.ends_at || new Date(s.ends_at).getTime() >= Date.now()
        );
        const fromUrl = live.find((s) => s.id === wanted && s.status === "open");
        const fromDay = day
          ? live.find((s) => s.status === "open" && moscowDate(s.starts_at) === day)
          : undefined;
        const open = fromUrl || fromDay || live.find((s) => s.status === "open");
        if (open) setSlotId(open.id);
      })
      .catch((err: Error) => setError(err.message));
  }, [params.id]);

  useEffect(() => {
    if (data?.name) document.title = `${data.name} · Букер`;
  }, [data]);

  async function request() {
    if (!getToken()) {
      router.push(loginHref(`/artists/${params.id}${slotId ? `?slot=${encodeURIComponent(slotId)}` : ""}`));
      return;
    }
    if (!slotId) {
      setError("Нет свободного слота");
      return;
    }
    try {
      setBusy(true);
      await api("/quick-request", {
        method: "POST",
        body: JSON.stringify({ artist_id: params.id, slot_id: slotId }),
      });
      router.push("/cabinet");
    } catch (err) {
      setError(err instanceof Error ? err.message : "Ошибка заявки");
    } finally {
      setBusy(false);
    }
  }

  if (!data) {
    return (
      <main>
        <h1>Профиль</h1>
        <p>{error || ""}</p>
        {!error ? (
          <div className="grid">
            <div className="skeleton" />
            <div className="skeleton" />
            <div className="skeleton" />
          </div>
        ) : null}
      </main>
    );
  }

  const rider = data.rider || {};

  return (
    <main>
      <p className="kicker">Профиль артиста</p>
      <h1>{data.name}</h1>
      <p>
        {data.city} · {CAT[data.category] || data.category}{" "}
        {data.verified ? <span className="chip ok">{CHIP.verified}</span> : <span className="chip wait">{CHIP.pending}</span>}
      </p>
      <p>{data.facts.note}</p>
      <p className="timeline">
        Ответ обычно: {data.facts.response || "данных пока мало"}. Завершённых сделок: {data.facts.deals ?? 0}.
      </p>
      <div className="grid" style={{ marginTop: 20 }}>
        <article className="card">
          <h2>Формат и состав</h2>
          <p>{rider.format || CAT[data.category] || "формат уточняется в Deal Room"}</p>
          <p>{rider.lineup || "состав: уточняется"}</p>
        </article>
        <article className="card tint">
          <h2>Райдер</h2>
          <p>{rider.tech || "Технический райдер согласуется после заявки. Это не цена."}</p>
        </article>
        <article className="card">
          <h2>Тарифы</h2>
          <ul>
            {data.tariffs.map((t) => (
              <li key={t.id}>
                {t.title}: {money(t.honorarium_rub)}
              </li>
            ))}
          </ul>
          <p className="timeline">Это ориентир. Итоговые условия поступят с сервера и будут связаны с quote_id.</p>
        </article>
      </div>
      <h2>Календарь</h2>
      <SlotList slots={data.slots} value={slotId} onChange={setSlotId} selectable highlightDay={wantedDay} />
      {!data.slots.some(
        (s) => s.status === "open" && (!s.ends_at || new Date(s.ends_at).getTime() >= Date.now())
      ) ? (
        <p style={{ display: "flex", gap: 8, flexWrap: "wrap", marginTop: 12 }}>
          <a className="btn secondary" href="mailto:hello@bukergo.ru?subject=Нет%20слота">
            Связаться с оператором
          </a>
        </p>
      ) : null}
      {error ? <p style={{ color: "var(--danger)" }}>{error}</p> : null}
      <p className="artist-desk-cta">
        <button type="button" onClick={() => void request()} disabled={!slotId || busy}>
          {busy ? "Отправляем заявку…" : "Запросить предложение"}
        </button>
      </p>
      <div className="sticky-cta">
        <button type="button" onClick={() => void request()} disabled={!slotId || busy}>
          {busy ? "Отправляем заявку…" : "Запросить предложение"}
        </button>
      </div>
    </main>
  );
}
