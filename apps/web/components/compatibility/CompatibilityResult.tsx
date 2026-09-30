import { formatWhen } from "@/lib/format";
export type CompatibilityCheck = { code: string; label: string; status: "compatible" | "attention" | "incompatible" | "unknown"; status_label: string; explanation: string };
export type CompatibilityData = { starts_at: string | null; ends_at: string | null; guest_count: number | null; status: CompatibilityCheck["status"]; status_label: string; score: number | null; methodology: string; note: string; checks: CompatibilityCheck[]; to_resolve: CompatibilityCheck[]; artist: { id: string; name: string }; venue: { id: string; name: string }; hall: { id: string; name: string } | null; halls: { id: string; name: string }[] };
const icons = { compatible: "✓", incompatible: "×", attention: "!", unknown: "?" };
export function CompatibilityResult({ data }: { data: CompatibilityData }) {
  return <section className="compatibility-result" aria-label="Результат совместимости">
    <div className="card"><p className="kicker">{data.artist.name} · {data.venue.name}{data.hall ? ` · ${data.hall.name}` : ""}</p><h2>Совместимость: {data.status_label.toLowerCase()}</h2>
      {data.score !== null && <p className="compatibility-score">{data.score}% <span>проверок подтвердили совпадение</span></p>}
      <p>{data.starts_at && data.ends_at ? `${formatWhen(data.starts_at)} — ${formatWhen(data.ends_at)}` : "Время события не задано"}{data.guest_count ? ` · ${data.guest_count} гостей` : " · число гостей не задано"}</p>
      <p className="timeline">{data.methodology}</p><p>{data.note}</p>
    </div>
    <div className="compatibility-checks">{data.checks.map((c) => <article key={c.code} className={`card compatibility-check compatibility-${c.status}`}><h3><span aria-hidden="true">{icons[c.status]}</span> {c.label}</h3><p><strong>{c.status_label}</strong></p><p>{c.explanation}</p></article>)}</div>
    <section className="card"><h2>Что нужно согласовать</h2>{data.to_resolve.length ? <ul>{data.to_resolve.map((c) => <li key={c.code}><strong>{c.label}:</strong> {c.explanation}</li>)}</ul> : <p>По введённым данным несоответствий нет. Зафиксируйте оборудование и временные окна в условиях сделки.</p>}</section>
  </section>;
}
