"use client";

import Link from "next/link";

export default function AppError({ reset }: { error: Error & { digest?: string }; reset: () => void }) {
  return (
    <main>
      <p className="kicker">Спотыкнулись. Не в споре — в коде.</p>
      <h1>Экран не собрался</h1>
      <p className="timeline">Сделку это не отменяет. Обновите страницу или уйдите в каталог.</p>
      <p style={{ display: "flex", gap: 8, flexWrap: "wrap" }}>
        <button type="button" onClick={() => reset()}>
          Ещё раз
        </button>
        <Link className="btn secondary" href="/search">
          Кто ещё не занят
        </Link>
      </p>
    </main>
  );
}
