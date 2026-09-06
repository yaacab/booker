"use client";

import { useEffect, useState } from "react";
import { moscowToday } from "@/lib/format";

/**
 * Поле даты hero-поиска. `min` выставляется только после маунта:
 * главная страница статическая, и «сегодня» нельзя запекать в разметку.
 */
export function HeroDateField() {
  const [min, setMin] = useState<string | undefined>(undefined);

  useEffect(() => {
    setMin(moscowToday());
  }, []);

  return (
    <label>
      Дата
      <input name="date" type="date" min={min} />
    </label>
  );
}
