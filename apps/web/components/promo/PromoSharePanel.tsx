"use client";

import Link from "next/link";
import { apiBase } from "@/lib/api";
import { ProfileMedia } from "@/components/ProfileMedia";
import { useEffect, useMemo, useRef, useState } from "react";
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

type ProfilePreview = { name: string; city?: string; media_url?: string | null; verified?: boolean; capacity?: number; facts?: { note?: string; deals?: number; response?: string } };

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
  const [copyError, setCopyError] = useState("");
  const [qrFailed, setQrFailed] = useState(false);
  const [retry, setRetry] = useState(0);
  const linkInput = useRef<HTMLInputElement>(null);
  const copyTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  useEffect(() => () => { if (copyTimer.current) clearTimeout(copyTimer.current); }, []);

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
    const controller = new AbortController();
    setPreview(null);
    setError("");
    fetch(`${apiBase()}${profilePath(kind, profileId)}`, { signal: controller.signal })
      .then(async (res) => {
        if (!res.ok) throw new Error(res.status === 404 ? "Профиль не найден или больше не опубликован." : "Не удалось загрузить профиль. Попробуйте ещё раз.");
        const json = await res.json();
        if (!json || typeof json.name !== "string") throw new Error("Не удалось загрузить профиль. Попробуйте ещё раз.");
        return json as ProfilePreview;
      })
      .then((json) => { if (!controller.signal.aborted) setPreview(json); })
      .catch((err: Error) => { if (!controller.signal.aborted) setError(err.message.includes("Профиль") || err.message.includes("Не удалось") ? err.message : "Не удалось загрузить профиль. Попробуйте ещё раз."); });
    return () => controller.abort();
  }, [kind, profileId, retry]);

  useEffect(() => { setCopied(false); setCopyError(""); setQrFailed(false); }, [shareUrl]);

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
      setCopyError("");
      if (copyTimer.current) clearTimeout(copyTimer.current);
      copyTimer.current = setTimeout(() => setCopied(false), 2500);
    } catch {
      setCopied(false);
      setCopyError("Выделили ссылку — скопируйте её через меню браузера или Ctrl/Cmd+C.");
      linkInput.current?.focus();
      linkInput.current?.select();
    }
  }

  const title = kind === "artist" ? "Поделиться артистом" : "Поделиться площадкой";

  return (
    <main className="promo-reference page-enter">
      <Link className="promo-back" href={publicPath}>Вернуться к профилю</Link>
      <div className="promo-layout">
        <header className="promo-intro">
          <h1>{title}</h1>
          <p>Отправьте профиль тем, с кем собираете событие. Посмотреть его можно без регистрации.</p>
          <dl className="promo-benefits">
            <div><dt>Открывается у всех</dt><dd>Даже без аккаунта в Букере</dd></div>
            <div><dt>Актуальный профиль</dt><dd>Информация обновляется вместе с профилем</dd></div>
            <div><dt>Удобно делиться</dt><dd>Ссылка для переписки и QR-код для встречи</dd></div>
          </dl>
        </header>
        <section className="promo-card" aria-label="Карточка для отправки">
          {error ? <div className="promo-load-error" role="alert"><h2>Профиль пока недоступен</h2><p>{error}</p><button type="button" className="btn secondary" onClick={() => setRetry(v => v + 1)}>Повторить загрузку</button></div>
            : preview ? <div className="promo-profile">
              <ProfileMedia src={preview.media_url} name={preview.name} compact />
              <div><h2>{preview.name}</h2>{preview.city && <p>{preview.city}</p>}
                {preview.verified && <span className="badge">Профиль подтверждён</span>}
                {preview.facts?.note && <p className="promo-note">{preview.facts.note}</p>}
                <dl className="promo-facts">
                  {kind === "venue" && preview.capacity != null && preview.capacity > 0 && <div><dt>Вместимость</dt><dd>До {preview.capacity} гостей</dd></div>}
                  {preview.facts?.deals != null && <div><dt>Завершённых сделок</dt><dd>{preview.facts.deals}</dd></div>}
                  {preview.facts?.response && <div><dt>Время ответа</dt><dd>{preview.facts.response}</dd></div>}
                </dl>
              </div>
            </div> : <p role="status" className="promo-loading">Загружаем профиль…</p>}
          <div className="promo-mediums" role="group" aria-label="Способ отправки">
            {MEDIUMS.map(item => <button key={item.id} type="button" aria-pressed={medium === item.id} onClick={() => setMedium(item.id)}>{item.label}</button>)}
          </div>
          <div className={`promo-share-tools${medium === "qr" ? " has-qr" : ""}`}>
            {medium === "qr" && <figure className="promo-qr">
              {qrFailed ? <p role="status">QR-код не загрузился. Воспользуйтесь ссылкой.</p> : <img key={qrSrc} src={qrSrc} width={180} height={180} alt="QR-код публичного профиля" onError={() => setQrFailed(true)} />}
              <figcaption>Откройте камеру телефона и наведите на код</figcaption>
            </figure>}
            <div className="promo-copy">
              <label htmlFor="promo-link">Ссылка на профиль</label>
              <input ref={linkInput} id="promo-link" readOnly value={shareUrl} onFocus={e => e.currentTarget.select()} />
              <button type="button" className="btn" onClick={() => void copyLink()}>{copied ? "Ссылка скопирована" : "Скопировать ссылку"}</button>
              <p className="promo-copy-notice" role="status">{copyError || (copied ? "Можно отправить её в переписку." : MEDIUMS.find(m => m.id === medium)?.hint)}</p>
              <Link className="promo-open" href={publicPath}>Открыть профиль</Link>
            </div>
          </div>
        </section>
      </div>
    </main>
  );
}
