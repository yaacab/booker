"use client";

import { useId, useState } from "react";
import Link from "next/link";

const pieces = [
  { label: "Артист", detail: "Ваш талант", icon: "mic", text: "Создайте профиль, покажите свои выступления и отметьте свободные даты.", href: "/login?mode=register&role=artist&next=%2Fcabinet%2Fperformer", action: "Создать профиль артиста" },
  { label: "Событие", detail: "Ваша идея", icon: "date", text: "Выберите артиста на нужную дату и расскажите о своём событии.", href: "/search?kind=artist", action: "Найти артиста" },
  { label: "Встреча", detail: "Всё сложилось", icon: "check", text: "Обсудите детали и подтвердите условия. Переписка и документы останутся в общей комнате сделки.", href: "#process-title", action: "Как это работает" },
];
const outline = "M30 40 H78 C85 40 78 16 100 16 C122 16 115 40 122 40 H170 Q180 40 180 50 V92 C180 101 204 88 204 112 C204 136 180 123 180 132 V170 Q180 180 170 180 H124 C115 180 128 155 104 155 C80 155 93 180 84 180 H30 Q20 180 20 170 V130 C20 123 44 135 44 112 C44 89 20 101 20 94 V50 Q20 40 30 40 Z";

export default function ArtistFirstHero() {
  const id = useId().replace(/:/g, "");
  const [selected, setSelected] = useState(0);
  return <section className="artist-first-hero" aria-labelledby="artist-first-title">
    <div className="artist-first-copy">
      <p className="eyebrow">Букер · люди, которые создают события</p>
      <h1 id="artist-first-title">Работа для артистов.<br /><em>Артисты для ваших событий.</em></h1>
      <p className="artist-first-description">Новые выступления, свободные даты и понятные договорённости — в одном месте.</p>
      <div className="artist-first-actions">
        <Link className="btn" href="/briefs">Я артист — хочу заказы <span aria-hidden="true">↗</span></Link>
        <Link className="btn secondary" href="/search?kind=artist">Мне нужен артист <span aria-hidden="true">↗</span></Link>
      </div>
      <p className="artist-first-register">Вы артист? <Link href="/login?mode=register&role=artist&next=%2Fcabinet%2Fperformer">Создайте профиль для заказчиков →</Link></p>
      <div className="artist-first-secondary"><Link href="/assemble">Собрать команду для события ↗</Link><Link href="/search?kind=venue">Найти площадку ↗</Link></div>
    </div>
    <div className="artist-first-art">
      <div className="artist-first-puzzles" role="group" aria-label="Как складывается выступление">
        {pieces.map((piece, i) => <button key={piece.icon} type="button" className={`artist-first-piece piece-${i}`} aria-pressed={selected === i} aria-controls="artist-first-detail" onClick={() => setSelected(i)}>
          <svg viewBox="0 0 224 205" aria-hidden="true">
            <defs>
              <linearGradient id={`${id}-${i}-chrome`} x1="0" y1="0" x2=".8" y2="1"><stop stopColor="#fcfff9"/><stop offset=".19" stopColor="#c1cbc0"/><stop offset=".34" stopColor="#fafff4"/><stop offset=".46" stopColor="#79887d"/><stop offset=".5" stopColor="#dfeada"/><stop offset=".8" stopColor="#eff9e8"/><stop offset="1" stopColor="#99a895"/></linearGradient>
              <linearGradient id={`${id}-${i}-edge`} x2="0" y2="1"><stop stopColor="#eef4ec"/><stop offset="1" stopColor="#586659"/></linearGradient>
            </defs>
            <path d={outline} transform="translate(0 7)" fill={`url(#${id}-${i}-edge)`}/>
            <path d={outline} fill={`url(#${id}-${i}-chrome)`} stroke="#f7fff1" strokeWidth="1.5"/>
            <text x="40" y="61" fill="#344638" fontSize="10">0{i + 1}</text>
            <g fill="none" stroke="#26392c" strokeWidth="3" strokeLinecap="round" strokeLinejoin="round">
              {piece.icon === "mic" ? <><rect x="95" y="66" width="18" height="29" rx="9"/><path d="M88 84v4a16 16 0 0 0 32 0v-4m-16 20v10m-9 0h18"/></> : piece.icon === "date" ? <><rect x="85" y="73" width="38" height="35" rx="5"/><path d="M85 84h38m-28-17v11m18-11v11m-17 17h5m7 0h5"/></> : <><circle cx="104" cy="88" r="22" fill="#d7ff75"/><path d="m93 88 7 7 15-16"/></>}
            </g>
          </svg>
          <span className="artist-first-piece-label"><strong>{piece.label}</strong><small>{piece.detail}</small></span>
        </button>)}
      </div>
      <div className="artist-first-detail" id="artist-first-detail" aria-live="polite"><p>{pieces[selected].text}</p><Link href={pieces[selected].href}>{pieces[selected].action} →</Link></div>
    </div>
  </section>;
}
