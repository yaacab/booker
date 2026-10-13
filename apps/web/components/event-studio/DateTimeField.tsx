"use client";

import { useEffect, useId, useRef, useState } from "react";

export function formatISODate(value: string) {
  return new Date(`${value}T12:00:00`).toLocaleDateString("ru-RU", {
    day: "numeric",
    month: "long",
    year: "numeric",
  });
}

const two = (value: number) => String(value).padStart(2, "0");
const iso = (date: Date) =>
  `${date.getFullYear()}-${two(date.getMonth() + 1)}-${two(date.getDate())}`;

function Calendar({
  value,
  min,
  onPick,
}: {
  value: string;
  min: string;
  onPick: (value: string) => void;
}) {
  const initial = value && value >= min ? value : min;
  const [month, setMonth] = useState(() => new Date(`${initial}T12:00:00`));
  const year = month.getFullYear();
  const monthIndex = month.getMonth();
  const start = new Date(year, monthIndex, 1, 12);
  const dayCount = new Date(year, monthIndex + 1, 0, 12).getDate();
  const offset = (start.getDay() + 6) % 7;
  const previous = new Date(year, monthIndex, 0, 12);
  const title = start.toLocaleDateString("ru-RU", { month: "long", year: "numeric" });

  return (
    <div className="es-picker-calendar">
      <div className="es-picker-month">
        <button
          type="button"
          aria-label="Предыдущий месяц"
          disabled={iso(previous) < min}
          onClick={() => setMonth(new Date(year, monthIndex - 1, 1, 12))}
        >
          ←
        </button>
        <strong aria-live="polite">{title}</strong>
        <button
          type="button"
          aria-label="Следующий месяц"
          onClick={() => setMonth(new Date(year, monthIndex + 1, 1, 12))}
        >
          →
        </button>
      </div>
      <div className="es-picker-weekdays" aria-hidden="true">
        {["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"].map((day) => (
          <span key={day}>{day}</span>
        ))}
      </div>
      <div className="es-picker-days" role="group" aria-label="Дни месяца">
        {Array.from({ length: offset }, (_, index) => (
          <span key={`blank-${index}`} />
        ))}
        {Array.from({ length: dayCount }, (_, index) => {
          const day = index + 1;
          const date = iso(new Date(year, monthIndex, day, 12));
          return (
            <button
              key={date}
              type="button"
              disabled={date < min}
              aria-label={formatISODate(date)}
              aria-pressed={date === value}
              className={date === value ? "is-selected" : ""}
              onClick={() => onPick(date)}
            >
              {day}
            </button>
          );
        })}
      </div>
    </div>
  );
}

function Wheel({
  label,
  count,
  value,
  onChange,
}: {
  label: string;
  count: number;
  value: number;
  onChange: (value: number) => void;
}) {
  const ref = useRef<HTMLDivElement>(null);
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  const initialized = useRef(false);

  useEffect(() => {
    const frame = requestAnimationFrame(() => {
      if (ref.current) ref.current.scrollTop = value * 44;
      initialized.current = true;
    });
    return () => cancelAnimationFrame(frame);
  }, []);

  useEffect(
    () => () => {
      if (timer.current) clearTimeout(timer.current);
    },
    [],
  );

  const choose = (next: number) => {
    const normalized = Math.max(0, Math.min(count - 1, next));
    onChange(normalized);
    ref.current?.scrollTo({ top: normalized * 44, behavior: "auto" });
  };

  return (
    <div className="es-time-column">
      <span>{label}</span>
      <div
        ref={ref}
        className="es-time-wheel"
        role="listbox"
        aria-label={label}
        tabIndex={0}
        onKeyDown={(event) => {
          if (event.key === "ArrowDown" || event.key === "ArrowUp") {
            event.preventDefault();
            choose(value + (event.key === "ArrowDown" ? 1 : -1));
          }
          if (event.key === "Home" || event.key === "End") {
            event.preventDefault();
            choose(event.key === "Home" ? 0 : count - 1);
          }
        }}
        onScroll={() => {
          if (!initialized.current) return;
          if (timer.current) clearTimeout(timer.current);
          timer.current = setTimeout(() => {
            const next = Math.max(
              0,
              Math.min(count - 1, Math.round((ref.current?.scrollTop ?? 0) / 44)),
            );
            onChange(next);
          }, 120);
        }}
      >
        {Array.from({ length: count }, (_, option) => (
          <button
            key={option}
            type="button"
            role="option"
            tabIndex={-1}
            aria-label={two(option)}
            aria-selected={option === value}
            className={option === value ? "is-selected" : ""}
            onClick={() => choose(option)}
          >
            {two(option)}
          </button>
        ))}
      </div>
    </div>
  );
}

function TimeWheel({ value, onPick }: { value: string; onPick: (value: string) => void }) {
  const [hours, setHours] = useState(Number((value || "18:00").split(":")[0]));
  const [minutes, setMinutes] = useState(Number((value || "18:00").split(":")[1]));

  return (
    <>
      <div className="es-time-preview" aria-live="polite">
        {two(hours)}:{two(minutes)}
      </div>
      <div className="es-time-wheels">
        <div className="es-time-center" aria-hidden="true" />
        <Wheel label="Часы" count={24} value={hours} onChange={setHours} />
        <b aria-hidden="true">:</b>
        <Wheel label="Минуты" count={60} value={minutes} onChange={setMinutes} />
      </div>
      <p className="es-picker-hint">
        Прокрутите часы и минуты или используйте стрелки на клавиатуре.
      </p>
      <button
        type="button"
        className="card-button es-picker-confirm"
        onClick={() => onPick(`${two(hours)}:${two(minutes)}`)}
      >
        Выбрать время
      </button>
    </>
  );
}

export function DateTimeField({
  label,
  kind,
  value,
  min,
  onChange,
}: {
  label: string;
  kind: "date" | "time";
  value: string;
  min?: string;
  onChange: (value: string) => void;
}) {
  const id = useId();
  const [open, setOpen] = useState(false);
  const dialog = useRef<HTMLDialogElement>(null);
  const trigger = useRef<HTMLButtonElement>(null);

  const close = () => {
    dialog.current?.close();
    setOpen(false);
    trigger.current?.focus({ preventScroll: true });
  };

  useEffect(() => {
    if (open && !dialog.current?.open) dialog.current?.showModal();
  }, [open]);

  const pick = (next: string) => {
    onChange(next);
    close();
  };
  const today = iso(new Date());

  return (
    <div className="es-picker-field">
      <label htmlFor={id}>{label}</label>
      <button
        ref={trigger}
        id={id}
        type="button"
        className="es-picker-trigger"
        aria-label={label}
        aria-haspopup="dialog"
        aria-expanded={open}
        onClick={() => setOpen(true)}
      >
        <span>
          {value
            ? kind === "date"
              ? formatISODate(value)
              : value
            : kind === "date"
              ? "Выбрать дату"
              : "Выбрать время"}
        </span>
        <span aria-hidden="true">{kind === "date" ? "▦" : "◷"}</span>
      </button>
      <dialog
        ref={dialog}
        className="es-picker-dialog"
        aria-labelledby={`${id}-title`}
        onCancel={(event) => {
          event.preventDefault();
          close();
        }}
        onClose={() => setOpen(false)}
        onClick={(event) => {
          if (event.target === event.currentTarget) close();
        }}
      >
        {open ? (
          <div className="es-picker-sheet">
            <div className="es-picker-heading">
              <h2 id={`${id}-title`}>
                {kind === "date" ? "Выберите дату" : "Выберите время"}
              </h2>
              <button type="button" aria-label="Закрыть выбор" onClick={close}>
                ×
              </button>
            </div>
            {kind === "date" ? (
              <Calendar value={value} min={min ?? today} onPick={pick} />
            ) : (
              <TimeWheel value={value} onPick={pick} />
            )}
          </div>
        ) : null}
      </dialog>
    </div>
  );
}
