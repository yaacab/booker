"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { CHIP } from "@/lib/copy";
import { money } from "@/lib/format";
import { SlotList } from "@/components/SlotList";

type Venue = {
  id: string;
  name: string;
  city: string;
  capacity: number;
  verified: boolean;
  facts: { note: string };
  tariffs: { id: string; title: string; honorarium_rub: number }[];
  slots: { id: string; hall: string; starts_at: string; ends_at?: string; status: string }[];
};

export default function VenuePage({ params }: { params: Promise<{ id: string }> }) {
  const [data, setData] = useState<Venue | null>(null);
  const [error, setError] = useState("");
  const [day, setDay] = useState<string | null>(null);

  useEffect(() => {
    setDay(new URLSearchParams(window.location.search).get("date"));
    void params.then((p) =>
      fetch(`${process.env.NEXT_PUBLIC_API_URL || "/api"}/venues/${p.id}`)
        .then((r) => (r.ok ? r.json() : Promise.reject(new Error("Не найдена"))))
        .then(setData)
        .catch((e: Error) => setError(e.message))
    );
  }, [params]);

  useEffect(() => {
    if (data?.name) document.title = `${data.name} · Букер`;
  }, [data]);

  if (!data) {
    return (
      <main>
        <h1>Площадка</h1>
        <p>{error || ""}</p>
        {!error ? (
          <div className="grid">
            <div className="skeleton" />
            <div className="skeleton" />
          </div>
        ) : null}
      </main>
    );
  }

  return (
    <main>
      <p className="kicker">Профиль площадки</p>
      <h1>{data.name}</h1>
      <p>
        {data.city} · до {data.capacity} гостей{" "}
        {data.verified ? <span className="chip ok">{CHIP.verified}</span> : <span className="chip wait">{CHIP.pending}</span>}
      </p>
      <p>{data.facts.note}</p>
      <h2>Тарифы</h2>
      <ul>
        {data.tariffs.map((t) => (
          <li key={t.id}>
            {t.title}: {money(t.honorarium_rub)}
          </li>
        ))}
      </ul>
      <h2>Календарь</h2>
      <SlotList slots={data.slots} highlightDay={day} />
      <p className="artist-desk-cta" style={{ marginTop: 16 }}>
        <Link className="btn" href={`/events/new?venue=need&roof=${encodeURIComponent(data.name)}`}>
          Создать заявку с этой площадкой
        </Link>
      </p>
      <div className="sticky-cta">
        <Link className="btn" href={`/events/new?venue=need&roof=${encodeURIComponent(data.name)}`}>
          Создать заявку с этой площадкой
        </Link>
      </div>
    </main>
  );
}
