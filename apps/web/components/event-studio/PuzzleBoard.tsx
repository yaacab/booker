"use client";

import { useEffect, useId, useMemo, useRef, useState } from "react";

export type PuzzleSlot = {
  id: string;
  label: string;
  detail?: string;
  filled: boolean;
};

export type PuzzleBoardProps = {
  slots: PuzzleSlot[];
  reducedMotion?: boolean;
  onSlotSelect?: (slot: PuzzleSlot) => void;
};

/** Flat / tab / blank — matches wooden reference interlocking (form only). */
type Side = 0 | 1 | -1;

const COLS = 3;
const ROWS = 2;
const W = 160;
const H = 160;
const OX = 78;
const OY = 44;
const TAB = 24;
const R = 18;

/** [top, right, bottom, left] per cell, row-major */
const LAYOUT: [Side, Side, Side, Side][] = [
  [0, 1, -1, 0],
  [0, 1, 1, -1],
  [0, 0, -1, -1],
  [1, 1, 0, 0],
  [-1, 1, 0, -1],
  [1, 0, 0, -1],
];

const GRADIENT_ANGLES = [118, 142, 98, 156, 124, 110];

function hEdge(x1: number, y: number, x2: number, side: Side, outward: number): string {
  if (side === 0) return `L ${x2} ${y}`;
  const mid = (x1 + x2) / 2;
  const dy = side * outward * TAB;
  const goingRight = x2 > x1;
  const a = goingRight ? mid - R : mid + R;
  const b = goingRight ? mid + R : mid - R;
  return [
    `L ${a} ${y}`,
    `C ${a} ${y} ${mid - (goingRight ? R * 0.35 : -R * 0.35)} ${y + dy} ${mid} ${y + dy}`,
    `C ${mid + (goingRight ? R * 0.35 : -R * 0.35)} ${y + dy} ${b} ${y} ${b} ${y}`,
    `L ${x2} ${y}`,
  ].join(" ");
}

function vEdge(x: number, y1: number, y2: number, side: Side, outward: number): string {
  if (side === 0) return `L ${x} ${y2}`;
  const mid = (y1 + y2) / 2;
  const dx = side * outward * TAB;
  const goingDown = y2 > y1;
  const a = goingDown ? mid - R : mid + R;
  const b = goingDown ? mid + R : mid - R;
  return [
    `L ${x} ${a}`,
    `C ${x} ${a} ${x + dx} ${mid - (goingDown ? R * 0.35 : -R * 0.35)} ${x + dx} ${mid}`,
    `C ${x + dx} ${mid + (goingDown ? R * 0.35 : -R * 0.35)} ${x} ${b} ${x} ${b}`,
    `L ${x} ${y2}`,
  ].join(" ");
}

function piecePath(col: number, row: number, sides: [Side, Side, Side, Side]): string {
  const x = OX + col * W;
  const y = OY + row * H;
  const [top, right, bottom, left] = sides;
  return [
    `M ${x} ${y}`,
    hEdge(x, y, x + W, top, -1),
    vEdge(x + W, y, y + H, right, 1),
    hEdge(x + W, y + H, x, bottom, 1),
    vEdge(x, y + H, y, left, -1),
    "Z",
  ].join(" ");
}

function labelPosition(index: number): { left: string; top: string } {
  const col = index % COLS;
  const row = Math.floor(index / COLS);
  const vbW = OX * 2 + COLS * W;
  const vbH = OY * 2 + ROWS * H;
  const cx = OX + col * W + W / 2;
  const cy = OY + row * H + H / 2;

  // Labels sit in gutters beside pieces — never drawn on chrome surfaces.
  if (col === 0) return { left: `${((OX * 0.48) / vbW) * 100}%`, top: `${(cy / vbH) * 100}%` };
  if (col === 2) return { left: `${((vbW - OX * 0.48) / vbW) * 100}%`, top: `${(cy / vbH) * 100}%` };
  if (row === 0) return { left: `${(cx / vbW) * 100}%`, top: `${((OY * 0.42) / vbH) * 100}%` };
  return { left: `${(cx / vbW) * 100}%`, top: `${((vbH - OY * 0.42) / vbH) * 100}%` };
}

export default function PuzzleBoard({ slots, reducedMotion = false, onSlotSelect }: PuzzleBoardProps) {
  const gradientId = useId().replace(/:/g, "");
  const padded = useMemo(
    () =>
      Array.from({ length: 6 }, (_, i) => slots[i] ?? {
        id: `empty-${i}`,
        label: "Слот",
        filled: false,
      }),
    [slots],
  );

  const fillKey = useMemo(
    () => padded.map((s) => `${s.id}:${s.filled ? 1 : 0}`).join("|"),
    [padded],
  );

  const previous = useRef(fillKey);
  const [motion, setMotion] = useState<Record<number, "assemble" | "release">>({});

  useEffect(() => {
    const next = puzzleTransitions(previous.current, fillKey);
    previous.current = fillKey;
    setMotion(reducedMotion ? {} : next);
    if (reducedMotion || Object.keys(next).length === 0) return;
    const t = window.setTimeout(() => setMotion({}), 440);
    return () => window.clearTimeout(t);
  }, [fillKey, reducedMotion]);

  const vbW = OX * 2 + COLS * W;
  const vbH = OY * 2 + ROWS * H;

  return (
    <div className={`puzzle-board${reducedMotion ? " puzzle-board--reduced" : ""}`}>
      <div
        className="puzzle-board-stage"
      >
        <svg
          className="puzzle-board-svg"
          viewBox={`0 0 ${vbW} ${vbH}`}
          xmlns="http://www.w3.org/2000/svg"
          aria-hidden="true"
        >
          <defs>
            {padded.map((slot, i) => {
              const angle = GRADIENT_ANGLES[i] ?? 120;
              return (
                <linearGradient
                  key={`g-${slot.id}`}
                  id={`${gradientId}-chrome-${i}`}
                  gradientTransform={`rotate(${angle} 0.5 0.5)`}
                  x1="0"
                  y1="0"
                  x2="1"
                  y2="1"
                >
                  <stop offset="0%" stopColor="var(--chrome-hi, #f2f4f7)" />
                  <stop offset="38%" stopColor="var(--chrome-mid, #b8bec8)" />
                  <stop offset="62%" stopColor="var(--chrome-hi, #f2f4f7)" />
                  <stop offset="100%" stopColor="var(--chrome-lo, #6e7582)" />
                </linearGradient>
              );
            })}
            {padded.map((_, i) => (
              <radialGradient key={`r-${i}`} id={`${gradientId}-sheen-${i}`} cx="32%" cy="28%" r="70%">
                <stop offset="0%" stopColor="#ffffff" stopOpacity="0.85" />
                <stop offset="45%" stopColor="var(--chrome-hi, #f2f4f7)" stopOpacity="0.35" />
                <stop offset="100%" stopColor="var(--chrome-lo, #6e7582)" stopOpacity="0.15" />
              </radialGradient>
            ))}
            <filter id={`${gradientId}-shadow`} x="-20%" y="-20%" width="140%" height="140%">
              <feDropShadow dx="0" dy="3" stdDeviation="3.5" floodColor="#4a5160" floodOpacity="0.35" />
            </filter>
          </defs>

          {LAYOUT.map((sides, i) => {
            const col = i % COLS;
            const row = Math.floor(i / COLS);
            const slot = padded[i];
            const filled = slot.filled;
            return (
              <g
                key={i}
                className={[
                  "puzzle-piece",
                  filled ? "puzzle-piece--filled" : "puzzle-piece--ghost",
                  motion[i] === "assemble" ? "puzzle-piece--snapping" : "",
                  motion[i] === "release" ? "puzzle-piece--releasing" : "",
                ]
                  .filter(Boolean)
                  .join(" ")}
              >
                <path
                  d={piecePath(col, row, sides)}
                  fill={filled ? `url(#${gradientId}-chrome-${i})` : "rgba(184, 190, 200, 0.08)"}
                  stroke={filled ? "var(--chrome-mid, #b8bec8)" : "var(--chrome-lo, #6e7582)"}
                  strokeWidth={filled ? 1.6 : 1.4}
                  strokeDasharray={filled ? undefined : "5 4"}
                  filter={filled ? `url(#${gradientId}-shadow)` : undefined}
                  opacity={filled ? 1 : 0.55}
                />
                {filled ? (
                  <path
                    d={piecePath(col, row, sides)}
                    fill={`url(#${gradientId}-sheen-${i})`}
                    stroke="none"
                    pointerEvents="none"
                  />
                ) : null}
              </g>
            );
          })}
        </svg>

        <ul className="puzzle-labels">
          {padded.map((slot, i) => {
            const pos = labelPosition(i);
            const side = i % COLS === 0 ? "left" : i % COLS === 2 ? "right" : "center";
            return (
              <li
                key={`label-${slot.id}`}
                className={`puzzle-label puzzle-label--${side}${slot.filled ? " is-filled" : ""}`}
                style={{ left: pos.left, top: pos.top }}
              >
                {onSlotSelect ? <button type="button" onClick={() => onSlotSelect(slot)} aria-label={`${slot.label}: ${slot.detail || (slot.filled ? "выбрано" : "добавить")}`}><strong>{slot.label}</strong>{slot.detail ? <span>{slot.detail}</span> : null}</button> : <><strong>{slot.label}</strong>{slot.detail ? <span>{slot.detail}</span> : null}</>}
              </li>
            );
          })}
        </ul>
      </div>
      {/* Состояние сборки доступно отдельно от интерактивных подписей. */}
      <ul className="sr-only">
        {padded.map((slot) => (
          <li key={`sr-${slot.id}`}>
            {slot.label}: {slot.filled ? `заполнено${slot.detail ? ` — ${slot.detail}` : ""}` : "пусто"}
          </li>
        ))}
      </ul>
    </div>
  );
}

/** Visual transitions only; selection never implies a reservation. */
export function puzzleTransitions(previous: string, current: string): Record<number, "assemble" | "release"> {
  const before = previous.split("|");
  return Object.fromEntries(current.split("|").flatMap<[number, "assemble" | "release"]>((slot, index) => {
    if (slot === before[index]) return [];
    if (slot.endsWith(":1")) return [[index, "assemble"]];
    if (before[index]?.endsWith(":1")) return [[index, "release"]];
    return [];
  }));
}

/** Build six puzzle slots from Event Studio draft fields. */
export function slotsFromDraft(input: {
  date: string;
  dateLabel: string;
  venueName?: string | null;
  hasVenue: boolean;
  talents: { id: string; roleLabel: string; name: string }[];
}): PuzzleSlot[] {
  const talentSlots: PuzzleSlot[] = [0, 1, 2, 3].map((i) => {
    const talent = input.talents[i];
    if (talent) {
      return {
        id: `talent-${talent.id}`,
        label: talent.roleLabel,
        detail: talent.name,
        filled: true,
      };
    }
    return {
      id: `talent-slot-${i}`,
      label: i === 0 ? "Роль" : `Роль ${i + 1}`,
      detail: "добавьте",
      filled: false,
    };
  });

  return [
    {
      id: "date",
      label: "Дата",
      detail: input.date ? input.dateLabel : "выберите",
      filled: Boolean(input.date),
    },
    {
      id: "venue",
      label: "Площадка",
      detail: input.hasVenue ? input.venueName || "выбрана" : "выберите",
      filled: input.hasVenue,
    },
    ...talentSlots,
  ];
}
