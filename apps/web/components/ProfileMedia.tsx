"use client";

import { useState } from "react";
import { initials } from "@/lib/format";

/** Только опубликованное владельцем медиа. Фото из макетов не выдаём за портфолио. */
export function ProfileMedia({ src, name, compact = false }: { src?: string | null; name: string; compact?: boolean }) {
  const [failedSrc, setFailedSrc] = useState<string | null>(null);
  const allowed = src && (src.startsWith("https://") || (src.startsWith("/") && !src.startsWith("//")));
  const hasMedia = Boolean(allowed && src !== failedSrc);
  return <div className={`profile-media${compact ? " is-compact" : ""}${hasMedia ? " has-media" : " has-placeholder"}`}>
    {allowed && src !== failedSrc ? <img src={src} alt={name} loading="lazy" decoding="async" referrerPolicy="no-referrer" onError={() => setFailedSrc(src)} />
      : <div className="profile-media-empty"><span className="profile-media-monogram" aria-hidden="true">{initials(name)}</span><span>Фотография пока не добавлена</span></div>}
    {hasMedia && !compact ? <span className="profile-media-caption">Фото профиля</span> : null}
  </div>;
}
