"use client";

import Link from "next/link";
import { Suspense, useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import { api, ApiError } from "@/lib/api";

type CompareColumn = {
  id: string;
  name: string;
  city: string;
  category: string;
  verified: boolean;
  capacity: number | string | null;
  honorarium_hint: string;
};

function CompareInner() {
  const params = useSearchParams();
  const targetType = (params.get("type") || "artist").toLowerCase();
  const idsParam = params.get("ids") || "";
  const ids = idsParam.split(",").map((s) => s.trim()).filter(Boolean);
  const [error, setError] = useState("");
  const [fields, setFields] = useState<string[]>([]);
  const [columns, setColumns] = useState<CompareColumn[]>([]);
  const [note, setNote] = useState("");
  const [ready, setReady] = useState(false);

  useEffect(() => {
    if (ids.length < 2) {
      setReady(true);
      setError("Добавьте 2–4 id через ?type=artist|venue&ids=a,b");
      return;
    }
    let cancelled = false;
    setReady(false);
    api<{ fields: string[]; columns: CompareColumn[]; note?: string }>(
      `/compare?target_type=${encodeURIComponent(targetType)}&ids=${encodeURIComponent(ids.join(","))}`,
    )
      .then((data) => {
        if (cancelled) return;
        setFields(data.fields || []);
        setColumns(data.columns || []);
        setNote(data.note || "");
        setError("");
      })
      .catch((e: Error) => {
        if (!cancelled) setError(e instanceof ApiError ? e.message : "Не удалось сравнить");
      })
      .finally(() => {
        if (!cancelled) setReady(true);
      });
    return () => {
      cancelled = true;
    };
  }, [targetType, idsParam]);

  return (
    <main>
      <p className="kicker">Букер</p>
      <h1>Сравнение</h1>
      <p className="timeline">2–4 кандидата одного типа. Неизвестные поля показаны явно.</p>
      <p>
        <Link className="btn secondary" href="/cabinet/customer/favorites">
          К избранному
        </Link>
      </p>
      {!ready ? <p>Загрузка…</p> : null}
      {error ? <p style={{ color: "var(--danger)" }}>{error}</p> : null}
      {columns.length > 0 ? (
        <div style={{ overflowX: "auto", marginTop: 16 }}>
          <table>
            <thead>
              <tr>
                <th>Поле</th>
                {columns.map((c) => (
                  <th key={c.id}>{c.name}</th>
                ))}
              </tr>
            </thead>
            <tbody>
              {fields
                .filter((f) => f !== "name")
                .map((field) => (
                  <tr key={field}>
                    <td>{field}</td>
                    {columns.map((c) => {
                      const raw = (c as Record<string, unknown>)[field];
                      const value =
                        raw === null || raw === undefined || raw === ""
                          ? "неизвестно"
                          : typeof raw === "boolean"
                            ? raw
                              ? "да"
                              : "нет"
                            : String(raw);
                      return <td key={`${c.id}-${field}`}>{value}</td>;
                    })}
                  </tr>
                ))}
            </tbody>
          </table>
          {note ? <p className="timeline">{note}</p> : null}
        </div>
      ) : null}
    </main>
  );
}

export default function ComparePage() {
  return (
    <Suspense fallback={<main><p>Загрузка…</p></main>}>
      <CompareInner />
    </Suspense>
  );
}
