import { useEffect, useRef, useState } from "react";

export function formatISODate(value: string) {
  return new Date(`${value}T12:00:00`).toLocaleDateString("ru-RU", { day: "numeric", month: "long", year: "numeric" });
}
const two = (n: number) => String(n).padStart(2, "0");
const iso = (d: Date) => `${d.getFullYear()}-${two(d.getMonth() + 1)}-${two(d.getDate())}`;

function Calendar({ value, min, onPick }: { value: string; min: string; onPick: (v: string) => void }) {
  const initial = value && value >= min ? value : min;
  const [month, setMonth] = useState(() => new Date(`${initial}T12:00:00`));
  const year = month.getFullYear(), m = month.getMonth();
  const start = new Date(year, m, 1, 12), end = new Date(year, m + 1, 0, 12).getDate();
  const offset = (start.getDay() + 6) % 7;
  const previous = new Date(year, m, 0, 12);
  const title = start.toLocaleDateString("ru-RU", { month: "long", year: "numeric" });
  return <div className="jr-picker-calendar">
    <div className="jr-picker-month">
      <button type="button" aria-label="Предыдущий месяц" disabled={iso(previous) < min} onClick={() => setMonth(new Date(year, m - 1, 1, 12))}>←</button>
      <strong aria-live="polite">{title}</strong>
      <button type="button" aria-label="Следующий месяц" onClick={() => setMonth(new Date(year, m + 1, 1, 12))}>→</button>
    </div>
    <div className="jr-picker-weekdays" aria-hidden="true">{["Пн", "Вт", "Ср", "Чт", "Пт", "Сб", "Вс"].map(d => <span key={d}>{d}</span>)}</div>
    <div className="jr-picker-days" role="group" aria-label="Дни месяца">
      {Array.from({ length: offset }, (_, k) => <span key={`blank-${k}`} />)}
      {Array.from({ length: end }, (_, k) => {
        const d = k + 1, date = iso(new Date(year, m, d, 12));
        return <button key={date} type="button" disabled={date < min} aria-label={formatISODate(date)}
          aria-pressed={date === value} className={date === value ? "is-selected" : ""}
          onClick={() => onPick(date)}>{d}</button>;
      })}
    </div>
  </div>;
}

function Wheel({ label, count, value, onChange }: { label: string; count: number; value: number; onChange: (n: number) => void }) {
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
  useEffect(() => () => { if (timer.current) clearTimeout(timer.current); }, []);
  const choose = (n: number) => {
    const v = Math.max(0, Math.min(count - 1, n));
    onChange(v);
    ref.current?.scrollTo({ top: v * 44, behavior: "auto" });
  };
  return <div className="jr-time-column"><span>{label}</span>
    <div ref={ref} className="jr-time-wheel" role="listbox" aria-label={label} tabIndex={0}
      onKeyDown={e => {
        if (e.key === "ArrowDown" || e.key === "ArrowUp") { e.preventDefault(); choose(value + (e.key === "ArrowDown" ? 1 : -1)); }
        if (e.key === "Home" || e.key === "End") { e.preventDefault(); choose(e.key === "Home" ? 0 : count - 1); }
      }} onScroll={() => {
        if (!initialized.current) return;
        if (timer.current) clearTimeout(timer.current);
        timer.current = setTimeout(() => {
          const n = Math.max(0, Math.min(count - 1, Math.round((ref.current?.scrollTop ?? 0) / 44)));
          onChange(n);
        }, 120);
      }}>
      {Array.from({ length: count }, (_, n) => <button key={n} type="button" role="option" tabIndex={-1}
        aria-label={two(n)} aria-selected={n === value} className={n === value ? "is-selected" : ""}
        onClick={() => choose(n)}>{two(n)}</button>)}
    </div>
  </div>;
}
function TimeWheel({ value, onPick }: { value: string; onPick: (v: string) => void }) {
  const [h, setH] = useState(Number((value || "18:00").split(":")[0]));
  const [m, setM] = useState(Number((value || "18:00").split(":")[1]));
  return <>
    <div className="jr-time-preview" aria-live="polite">{two(h)}:{two(m)}</div>
    <div className="jr-time-wheels"><div className="jr-time-center" aria-hidden="true" />
      <Wheel label="Часы" count={24} value={h} onChange={setH} /><b aria-hidden="true">:</b>
      <Wheel label="Минуты" count={60} value={m} onChange={setM} />
    </div>
    <p className="jr-picker-hint">Прокрутите часы и минуты или используйте стрелки на клавиатуре.</p>
    <button type="button" className="jr-btn" onClick={() => onPick(`${two(h)}:${two(m)}`)}>Выбрать время</button>
  </>;
}

export function DateTimeField({ label, kind, value, min, onChange }: {
  label: string; kind: "date" | "time"; value: string; min?: string; onChange: (v: string) => void;
}) {
  const [open, setOpen] = useState(false);
  const [id] = useState(() => `picker-${crypto.randomUUID()}`);
  const dialog = useRef<HTMLDialogElement>(null);
  const trigger = useRef<HTMLButtonElement>(null);
  const close = () => { dialog.current?.close(); setOpen(false); trigger.current?.focus({ preventScroll: true }); };
  useEffect(() => { if (open && !dialog.current?.open) dialog.current?.showModal(); }, [open]);
  const pick = (v: string) => { onChange(v); close(); };
  const today = iso(new Date());
  return <div className="jr-picker-field">
    <label htmlFor={id}>{label}</label>
    <button ref={trigger} id={id} type="button" className="jr-picker-trigger" aria-label={label}
      aria-haspopup="dialog" aria-expanded={open} onClick={() => setOpen(true)}>
      <span>{value ? (kind === "date" ? formatISODate(value) : value) : (kind === "date" ? "Выбрать дату" : "Выбрать время")}</span>
      <span aria-hidden="true">{kind === "date" ? "▦" : "◷"}</span>
    </button>
    <dialog ref={dialog} className="jr-picker-dialog" aria-labelledby={`${id}-title`}
      onCancel={e => { e.preventDefault(); close(); }} onClose={() => setOpen(false)}
      onClick={e => { if (e.target === e.currentTarget) close(); }}>
      {open && <div className="jr-picker-sheet">
        <div className="jr-picker-heading"><h2 id={`${id}-title`}>{kind === "date" ? "Выберите дату" : "Выберите время"}</h2>
          <button type="button" aria-label="Закрыть выбор" onClick={close}>×</button></div>
        {kind === "date" ? <Calendar value={value} min={min ?? today} onPick={pick} /> : <TimeWheel value={value} onPick={pick} />}
      </div>}
    </dialog>
  </div>;
}
