"use client";

import type { DealRoomAccentView } from "@/lib/dealRoomAccents";

export function DealRoomAccentGrid({ accents }: { accents: DealRoomAccentView[] }) {
  return (
    <div className="deal-accent-grid" data-testid="deal-room-accents">
      {accents.map((accent) => (
        <article key={accent.id} className="card deal-accent-card" data-accent={accent.id}>
          <header className="deal-accent-head">
            <h3>{accent.title}</h3>
            <p className="timeline">{accent.hint}</p>
          </header>
          <p>
            <strong>{accent.body}</strong>
          </p>
          {accent.detail ? <p className="timeline">{accent.detail}</p> : null}
        </article>
      ))}
    </div>
  );
}
