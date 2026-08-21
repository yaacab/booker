"use client";

import { useEffect, useRef } from "react";
import { formatClock, formatDay, moscowDate } from "@/lib/format";

export type SlotRow = {
  id: string;
  starts_at: string;
  ends_at?: string;
  status: string;
  hall?: string;
};

function statusCopy(status: string): { label: string; cls: string } {
  if (status === "open") return { label: "свободен", cls: "ok" };
  if (status === "held") return { label: "hold", cls: "wait" };
  if (status === "confirmed") return { label: "занят", cls: "live" };
  return { label: status, cls: "live" };
}

function groups(slots: SlotRow[]): { day: string; items: SlotRow[] }[] {
  const now = Date.now();
  const ordered = [...slots]
    .filter((s) => {
      if (!s.ends_at) return true;
      if (s.status === "open" && new Date(s.ends_at).getTime() < now) return false;
      return new Date(s.ends_at).getTime() >= now - 60 * 60 * 1000;
    })
    .sort((a, b) => a.starts_at.localeCompare(b.starts_at));
  const map = new Map<string, SlotRow[]>();
  for (const s of ordered) {
    const day = formatDay(s.starts_at);
    const list = map.get(day) || [];
    list.push(s);
    map.set(day, list);
  }
  return [...map.entries()].map(([day, items]) => ({ day, items }));
}

export function SlotList({
  slots,
  value,
  onChange,
  selectable = false,
  highlightDay,
}: {
  slots: SlotRow[];
  value?: string;
  onChange?: (id: string) => void;
  selectable?: boolean;
  highlightDay?: string | null;
}) {
  const hitRef = useRef<HTMLElement | null>(null);

  useEffect(() => {
    if (!hitRef.current) return;
    const reduce = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    hitRef.current.scrollIntoView({ block: "nearest", behavior: reduce ? "auto" : "smooth" });
  }, [highlightDay, slots]);
  if (!slots.length) {
    return (
      <p className="timeline">
        Календарь пуст. Либо всё разобрали, либо человек ещё не проставил дырки.
      </p>
    );
  }

  const days = groups(slots);
  if (!days.length) {
    return (
      <p className="timeline">
        Живых слотов нет: всё либо прошло, либо уже чужое. Другая дата — или зовите человека.
      </p>
    );
  }

  return (
    <div className="slot-groups">
      {days.map((g) => {
        const hit = Boolean(highlightDay && g.items.some((s) => moscowDate(s.starts_at) === highlightDay));
        return (
        <section
          key={g.day}
          ref={hit ? (el) => { hitRef.current = el; } : undefined}
          className={hit ? "slot-day-hit" : undefined}
        >
          <h3 className="slot-day">{g.day}{hit ? " · эта дата" : ""}</h3>
          <ul className="slot-list">
            {g.items.map((s) => {
              const st = statusCopy(s.status);
              const open = s.status === "open";
              const on = value === s.id;
              const inner = (
                <>
                  <span className="slot-when">
                    {s.hall ? `${s.hall} · ` : ""}
                    {formatClock(s.starts_at)}
                    <span className="timeline"> МСК</span>
                  </span>
                  <span className={`chip ${st.cls}`}>{st.label}</span>
                </>
              );
              return (
                <li key={s.id}>
                  {selectable && open ? (
                    <button
                      type="button"
                      className={`slot-btn${on ? " on" : ""}`}
                      onClick={() => onChange?.(s.id)}
                      aria-pressed={on}
                    >
                      {inner}
                    </button>
                  ) : (
                    <div className={`slot-btn${open ? "" : " locked"}`}>{inner}</div>
                  )}
                </li>
              );
            })}
          </ul>
        </section>
        );
      })}
    </div>
  );
}
