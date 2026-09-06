"use client";

import { useCallback, useEffect, useState, type MouseEvent } from "react";
import { useRouter } from "next/navigation";
import { api, getToken } from "@/lib/api";
import { loginHref } from "@/lib/next";

export type FavoriteTargetType = "artist" | "venue";

type FavoriteItem = {
  id: string;
  target_type: FavoriteTargetType;
  target_id: string;
};

type FavoriteToggleProps = {
  targetType: FavoriteTargetType;
  targetId: string;
  /** Compact chip on catalog cards; default is secondary button for profiles. */
  compact?: boolean;
  className?: string;
  onChanged?: (favorited: boolean) => void;
};

export function FavoriteToggle({
  targetType,
  targetId,
  compact = false,
  className,
  onChanged,
}: FavoriteToggleProps) {
  const router = useRouter();
  const [ready, setReady] = useState(false);
  const [signedIn, setSignedIn] = useState(false);
  const [favoriteId, setFavoriteId] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");

  const refresh = useCallback(async () => {
    if (!getToken()) {
      setSignedIn(false);
      setFavoriteId(null);
      setReady(true);
      return;
    }
    setSignedIn(true);
    try {
      const res = await api<{ items: FavoriteItem[] }>(
        `/favorites?target_type=${encodeURIComponent(targetType)}&target_id=${encodeURIComponent(targetId)}`,
      );
      const hit = res.items?.[0];
      setFavoriteId(hit?.id ?? null);
      setError("");
    } catch {
      setFavoriteId(null);
    } finally {
      setReady(true);
    }
  }, [targetId, targetType]);

  useEffect(() => {
    void refresh();
  }, [refresh]);

  async function toggle(e: MouseEvent) {
    e.preventDefault();
    e.stopPropagation();
    if (!getToken()) {
      const path =
        targetType === "artist" ? `/artists/${targetId}` : `/venues/${targetId}`;
      router.push(loginHref(path));
      return;
    }
    if (busy) return;
    setBusy(true);
    setError("");
    try {
      if (favoriteId) {
        await api(`/favorites/${favoriteId}`, { method: "DELETE" });
        setFavoriteId(null);
        onChanged?.(false);
      } else {
        const created = await api<FavoriteItem>("/favorites", {
          method: "POST",
          body: JSON.stringify({ target_type: targetType, target_id: targetId }),
        });
        setFavoriteId(created.id);
        onChanged?.(true);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : "Не удалось обновить избранное");
    } finally {
      setBusy(false);
    }
  }

  const active = Boolean(favoriteId);
  const label = !signedIn ? "В избранное" : active ? "В избранном" : "В избранное";

  return (
    <span className={className} style={{ display: "inline-flex", flexDirection: "column", gap: 4 }}>
      <button
        type="button"
        className={compact ? `chip ${active ? "ok" : "wait"}` : "btn secondary"}
        onClick={(e) => void toggle(e)}
        disabled={busy || !ready}
        aria-pressed={active}
        aria-label={active ? "Убрать из избранного" : "Добавить в избранное"}
        style={compact ? { cursor: "pointer", border: "none" } : undefined}
      >
        {busy ? "…" : label}
      </button>
      {error ? (
        <span className="timeline" style={{ color: "var(--danger)", fontSize: 12 }}>
          {error}
        </span>
      ) : null}
    </span>
  );
}
