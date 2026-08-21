"use client";

import Link from "next/link";

export default function AppError({ reset }: { error: Error & { digest?: string }; reset: () => void }) {
  return (
    <main>
      <p className="kicker">Техническая ошибка</p>
      <h1>Не удалось открыть экран</h1>
      <p className="timeline">Данные сделки не изменены. Повторите попытку или вернитесь в каталог.</p>
      <p style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
        <button type="button" onClick={() => reset()}>
          Ещё раз
        </button>
        <Link className="btn secondary" href="/search">
          Открыть каталог
        </Link>
      </p>
    </main>
  );
}
