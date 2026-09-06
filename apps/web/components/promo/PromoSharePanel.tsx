"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import {
  buildShareUrl,
  profilePath,
  qrCodeImageUrl,
  trackPromoEvent,
  type ProfileKind,
  type PromoMedium,
} from "@/lib/promo";

type Props = {
  kind: ProfileKind;
  profileId: string;
  hallId?: string;
  tariffId?: string;
};

type ProfilePreview = { name: string; city?: string };

const MEDIUMS: { id: PromoMedium; label: string; hint: string }[] = [
  { id: "link", label: "Ссылка", hint: "Мессенджер или email" },
  { id: "qr", label: "QR-код", hint: "Визитка, стойка, афиша" },
  { id: "social", label: "Соцсети", hint: "Пост или сторис" },
];

export function PromoSharePanel({ kind, profileId, hallId, tariffId }: Props) {
  const [medium, setMedium] = useState<PromoMedium>("qr");
  const [preview, setPreview] = useState<ProfilePreview | null>(null);
  const [error, setError] = useState("");
  const [copied, setCopied] = useState(false);

  const shareUrl = useMemo(
    () => buildShareUrl(kind, profileId, { medium, hallId, tariffId }),
    [kind, profileId, medium, hallId, tariffId],
  );
  const qrSrc = useMemo(() => qrCodeImageUrl(shareUrl, 260), [shareUrl]);
  const publicPath = profilePath(kind, profileId);

  useEffect(() => {
    trackPromoEvent("promo.share.view", {
      profile_kind: kind,
      profile_id: profileId,
      medium,
      source: "booker_share",
    });
  }, [kind, profileId, medium]);

  useEffect(() => {
    if (medium === "qr") {
      trackPromoEvent("promo.qr.display", {
        profile_kind: kind,
        profile_id: profileId,
        medium: "qr",
        source: "booker_share",
      });
    }
  }, [kind, profileId, medium, shareUrl]);

  useEffect(() => {
    const endpoint = kind === "artist" ? `/artists/${profileId}` : `/venues/${profileId}`;
    fetch(`${process.env.NEXT_PUBLIC_API_URL || "/api"}${endpoint}`)
      .then((res) => (res.ok ? res.json() : Promise.reject(new Error("Не найден"))))
      .then((json: ProfilePreview) => setPreview(json))
      .catch((err: Error) => setError(err.message));
  }, [kind, profileId]);

  async function copyLink() {
    try {
      await navigator.clipboard.writeText(shareUrl);
      setCopied(true);
      trackPromoEvent("promo.link.copy", {
        profile_kind: kind,
        profile_id: profileId,
        medium,
        source: "booker_share",
      });
      window.setTimeout(() => setCopied(false), 2000);
    } catch {
      setCopied(false);
    }
  }

  const title = kind === "artist" ? "Поделиться профилем артиста" : "Поделиться профилем площадки";

  return (
    <main>
      <p className="eyebrow">Органическое продвижение</p>
      <h1>{title}</h1>
      {preview ? (
        <p className="muted">
          {preview.name}
          {preview.city ? ` · ${preview.city}` : ""}
        </p>
      ) : null}
      {error ? <p style={{ color: "var(--danger)" }}>{error}</p> : null}

      <section className="card surface-glass" style={{ display: "grid", gap: "1rem", maxWidth: 640 }}>
        <div style={{ display: "flex", flexWrap: "wrap", gap: "0.5rem" }} role="tablist" aria-label="Источник ссылки">
          {MEDIUMS.map((item) => (
            <button
              key={item.id}
              type="button"
              role="tab"
              aria-selected={medium === item.id}
              className={medium === item.id ? "btn" : "btn secondary"}
              onClick={() => setMedium(item.id)}
            >
              {item.label}
            </button>
          ))}
        </div>
        <p className="muted">{MEDIUMS.find((m) => m.id === medium)?.hint}</p>

        <label style={{ display: "grid", gap: "0.5rem" }}>
          <span>Публичная ссылка с отслеживанием источника</span>
          <div style={{ display: "flex", flexWrap: "wrap", gap: "0.5rem" }}>
            <input
              readOnly
              value={shareUrl}
              aria-label="Ссылка для sharing"
              style={{ flex: "1 1 220px", fontFamily: "var(--mono)", fontSize: "0.85rem" }}
            />
            <button type="button" className="btn secondary" onClick={() => void copyLink()}>
              {copied ? "Скопировано" : "Копировать"}
            </button>
          </div>
        </label>

        {medium === "qr" ? (
          <figure style={{ margin: 0, textAlign: "center" }}>
            {/* eslint-disable-next-line @next/next/no-img-element */}
            <img src={qrSrc} width={260} height={260} alt="QR-код публичного профиля" loading="lazy" />
            <figcaption className="muted" style={{ marginTop: "0.5rem" }}>
              Сканирование ведёт на публичный профиль с меткой источника
            </figcaption>
          </figure>
        ) : null}

        <p className="muted">
          В URL нет email и телефона — только метки utm_source, utm_medium и utm_campaign для воронки
          «просмотр → заявка».
        </p>

        <div style={{ display: "flex", flexWrap: "wrap", gap: "0.5rem" }}>
          <Link className="btn secondary" href={publicPath}>
            Открыть профиль
          </Link>
          <Link className="btn" href={publicPath} target="_blank" rel="noopener noreferrer">
            Предпросмотр как гость
          </Link>
        </div>
      </section>
    </main>
  );
}
