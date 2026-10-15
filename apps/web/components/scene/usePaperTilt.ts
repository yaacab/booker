"use client";

import { useEffect, type RefObject } from "react";
import { MOTION, prefersReducedMotion } from "@/lib/motion";

/** Desktop-only paper tilt (≤5°). Writes --bk-rx/--bk-ry; CSS applies the
 *  transform. Touch devices get the CSS lift instead; reduced motion gets none. */
export function usePaperTilt(ref: RefObject<HTMLElement | null>) {
  useEffect(() => {
    const el = ref.current;
    if (!el || typeof window === "undefined") return;
    if (!window.matchMedia?.("(hover: hover) and (pointer: fine)").matches || prefersReducedMotion()) return;
    let raf = 0;
    const max = MOTION.tiltMaxDeg;
    const move = (e: PointerEvent) => {
      const b = el.getBoundingClientRect();
      const px = (e.clientX - b.left) / b.width - 0.5;
      const py = (e.clientY - b.top) / b.height - 0.5;
      cancelAnimationFrame(raf);
      raf = requestAnimationFrame(() => {
        el.style.setProperty("--bk-ry", `${(px * 2 * max * 0.8).toFixed(2)}deg`);
        el.style.setProperty("--bk-rx", `${(-py * 2 * max * 0.6).toFixed(2)}deg`);
      });
    };
    const leave = () => { cancelAnimationFrame(raf); el.style.removeProperty("--bk-rx"); el.style.removeProperty("--bk-ry"); };
    el.classList.add("bk-tilt");
    el.addEventListener("pointermove", move);
    el.addEventListener("pointerleave", leave);
    return () => { leave(); el.classList.remove("bk-tilt"); el.removeEventListener("pointermove", move); el.removeEventListener("pointerleave", leave); };
  }, [ref]);
}
