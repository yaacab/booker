"use client";

import Link from "next/link";

export default function AppError({ reset }: { error: Error & { digest?: string }; reset: () => void }) {
  return (
    <main className="reference-empty">
      <p className="kicker">Техническая ошибка</p>
      <h1>Не удалось открыть экран</h1>
      <p className="timeline">Повторите попытку. Если ошибка сохраняется, напишите в поддержку.</p>
      <p style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
        <button type="button" onClick={() => reset()}>
          Ещё раз
        </button>
        <Link className="btn secondary" href="/search">
          Открыть каталог
        </Link>
        <Link className="btn secondary" href="/support">Поддержка</Link>
      </p>
    </main>
  );
}
