"use client";

import { useEffect, useState } from "react";
import { formatWhen, holdRemaining } from "@/lib/format";

export function HoldCountdown({ expiresAt }: { expiresAt: string }) {
  const [label, setLabel] = useState(() => holdRemaining(expiresAt));

  useEffect(() => {
    const tick = () => setLabel(holdRemaining(expiresAt));
    tick();
    const id = setInterval(tick, 1000);
    return () => clearInterval(id);
  }, [expiresAt]);

  return (
    <p className="mono hold-gold">
      hold до {formatWhen(expiresAt)} · {label}
    </p>
  );
}
