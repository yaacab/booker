"use client";

import { useEffect, useRef } from "react";
import { useSearchParams } from "next/navigation";
import { parsePromoAttribution, trackPromoEvent, type ProfileKind } from "@/lib/promo";

type Props = {
  kind: ProfileKind;
  profileId: string;
};

/** Fires promo.profile.open once when landing from a booker_share link. Wire into public profiles. */
export function PromoAttributionBeacon({ kind, profileId }: Props) {
  const searchParams = useSearchParams();
  const fired = useRef(false);

  useEffect(() => {
    if (fired.current) return;
    const attribution = parsePromoAttribution(searchParams);
    if (!attribution) return;
    fired.current = true;
    trackPromoEvent("promo.profile.open", {
      profile_kind: kind,
      profile_id: profileId,
      medium: attribution.medium,
      source: attribution.source,
    });
  }, [kind, profileId, searchParams]);

  return null;
}
