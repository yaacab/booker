"use client";

import "./globals.css";

export default function GlobalError({ reset }: { error: Error & { digest?: string }; reset: () => void }) {
  return (
    <html lang="ru">
      <body>
        <main className="wrap" style={{ paddingTop: 48 }}>
          <p className="kicker">Спотыкнулись. Не в споре — в коде.</p>
          <h1>Букер не открылся</h1>
          <p className="timeline">Сделку это не отменяет. Можно ткнуть ещё раз.</p>
          <p>
            <button type="button" onClick={() => reset()}>
              Ещё раз
            </button>
          </p>
        </main>
      </body>
    </html>
  );
}
