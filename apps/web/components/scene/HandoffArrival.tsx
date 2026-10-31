"use client";

import { useLayoutEffect, useRef, type ReactNode } from "react";
import { MOTION, playArrival, takeHandoff } from "@/lib/motion";

/** Shared-element arrival: if the previous screen left a fresh handoff for this
 *  channel/id, the wrapped element grows from that rectangle (FLIP). Otherwise it
 *  appears instantly. Never delays content or interaction. */
export function HandoffArrival({ channel, id, className = "", duration = MOTION.cover, onArrive, children }: {
  channel: string; id: string; className?: string; duration?: number;
  onArrive?: (hadHandoff: boolean) => void; children: ReactNode;
}) {
  const ref = useRef<HTMLDivElement>(null);
  useLayoutEffect(() => {
    const el = ref.current;
    if (!el) return;
    const handoff = takeHandoff(channel, (d) => d.id === id);
    if (handoff) {
      /* the cover must be the first thing seen: start the new page at its top */
      if (window.scrollY > 0 && el.getBoundingClientRect().top < 0) window.scrollTo({ top: 0, behavior: "instant" as ScrollBehavior });
      const b = el.getBoundingClientRect();
      const visible = b.bottom > 0 && b.top < window.innerHeight;
      playArrival(el, visible ? handoff.rect : null, duration);
      el.dataset.arrived = "handoff";
    }
    onArrive?.(Boolean(handoff));
    // run once per mounted target
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [channel, id]);
  return <div ref={ref} className={`bk-arrival ${className}`.trim()}>{children}</div>;
}
