"use client";
import Link from "next/link";
import { useEffect, useState } from "react";
export function ProfileCompareButton({ targetType, targetId }: { targetType: "artist" | "venue"; targetId: string }) {
  const [ids, setIds] = useState<string[]>([]); const [message, setMessage] = useState("");
  const key = `booker.${targetType}-compare`;
  useEffect(() => { try { const value: unknown = JSON.parse(localStorage.getItem(key) || "[]"); if (Array.isArray(value)) setIds(value.filter((id): id is string => typeof id === "string").slice(0, 4)); } catch { /* optional selection */ } }, [key]);
  function toggle() { const next = ids.includes(targetId) ? ids.filter((id) => id !== targetId) : [...ids, targetId].slice(-4); setIds(next); try { localStorage.setItem(key, JSON.stringify(next)); } catch { /* retain in memory */ } setMessage(next.length < 2 ? "Выберите ещё один профиль для сравнения." : "Можно открыть сравнение выбранных профилей."); }
  return <><button className="secondary" type="button" aria-pressed={ids.includes(targetId)} onClick={toggle}>{ids.includes(targetId) ? "Убрать из сравнения" : "Сравнить"}</button>{ids.length >= 2 && <Link className="btn secondary" href={`/compare?type=${targetType}&ids=${encodeURIComponent(ids.join(","))}`}>Сравнение ({ids.length})</Link>}{message && <span role="status" className="timeline">{message}</span>}</>;
}
