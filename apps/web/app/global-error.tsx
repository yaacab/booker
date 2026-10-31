"use client";

import "./globals.css";
import "./reference-puzzles.css";

export default function GlobalError({ reset }: { error: Error & { digest?: string }; reset: () => void }) {
  return (
    <html lang="ru">
      <body>
        <main className="wrap" style={{ paddingTop: 48 }}>
          <p className="kicker">Техническая ошибка</p>
          <h1>Букер временно недоступен</h1>
          <p className="timeline">Попробуйте загрузить страницу ещё раз. Если ошибка повторяется, вернитесь позже.</p>
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
