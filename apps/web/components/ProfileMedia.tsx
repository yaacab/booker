"use client";

import { useState } from "react";

/** Только опубликованное владельцем медиа. Фото из макетов не выдаём за портфолио. */
export function ProfileMedia({ src, name, compact = false }: { src?: string | null; name: string; compact?: boolean }) {
  const [failedSrc, setFailedSrc] = useState<string | null>(null);
  const allowed = src && (src.startsWith("https://") || (src.startsWith("/") && !src.startsWith("//")));
  return <div className={`profile-media${compact ? " is-compact" : ""}`}>
    {allowed && src !== failedSrc ? <img src={src} alt={name} loading="lazy" decoding="async" referrerPolicy="no-referrer" onError={() => setFailedSrc(src)} />
      : <div className="profile-media-empty"><strong>{name}</strong><span>Фотография пока не добавлена</span></div>}
  </div>;
}
