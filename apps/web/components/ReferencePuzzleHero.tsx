"use client";

import { useState } from "react";
import Image from "next/image";
import Link from "next/link";

const pieces = [
  { id: "dj", name: "Диджей", detail: "Создаёт атмосферу", caption: "Музыка объединяет" },
  { id: "venue", name: "Площадка", detail: "Даёт пространство", caption: "Пространство вдохновляет" },
  { id: "photographer", name: "Фотограф", detail: "Сохраняет эмоции", caption: "Эмоции остаются" },
] as const;

/** Local visual selection only: not a supplier selection, request, hold or booking. */
export function ReferencePuzzleHero() {
  const [selected, setSelected] = useState<string | null>(null);
  const toggle = (id: string) => setSelected(current => current === id ? null : id);
  return (
    <section className="reference-hero" aria-labelledby="home-title">
      <div className="reference-heading">
        <h1 id="home-title">Нужные люди.<br />Подходящее место.<br />Один клик.</h1>
        <p className="reference-manifesto">Больше<br />событий<br />для людей</p>
        <p className="reference-description">Находим артистов и площадки.<br />Собираем команду для вашего<br className="desktop-break" /> события — просто, по-человечески.</p>
      </div>
      <div className="reference-assembly">
        <aside className="team-legend" aria-label="Состав команды">
          <h2>Ваша команда</h2>
          {pieces.map((piece, index) => (
            <button type="button" key={piece.id} aria-pressed={selected === piece.id} aria-controls={`puzzle-${piece.id}`} onClick={() => toggle(piece.id)}>
              <span className="team-index" aria-hidden="true">0{index + 1}</span>
              <span><strong>{piece.name}</strong><small>{piece.detail}</small></span>
            </button>
          ))}
        </aside>
        <div className="reference-pieces" role="group" aria-label="Пазлы команды" aria-describedby="puzzle-help" onKeyDown={event => { if (event.key === "Escape") setSelected(null); }}>
          {pieces.map(piece => (
            <button type="button" id={`puzzle-${piece.id}`} key={piece.id} className="reference-piece" aria-label={piece.name} aria-pressed={selected === piece.id} onClick={() => toggle(piece.id)}>
              <Image src={`/design/puzzle-${piece.id}.png`} alt="" width={1280} height={1280} priority sizes="(max-width: 600px) 42vw, (max-width: 900px) 35vw, 430px" />
              <span className="piece-label"><strong>{piece.name}</strong><small>{piece.caption}</small></span>
            </button>
          ))}
        </div>
      </div>
      <div className="reference-action">
        <p id="puzzle-help">Нажмите на пазл — почувствуйте, как всё складывается</p>
        <Link className="btn reference-cta" href="/events/new?event_studio_map_v1=1">Собрать событие <span aria-hidden="true">→</span></Link>
        <p className="reference-footnote">Москва · Образы категорий, не реальные предложения</p>
      </div>
    </section>
  );
}
