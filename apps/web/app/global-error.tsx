"use client";

import "./globals.css";

export default function GlobalError({ reset }: { error: Error & { digest?: string }; reset: () => void }) {
  return (
    <html lang="ru">
      <body>
        <main className="wrap" style={{ paddingTop: 48 }}>
          <p className="kicker">Техническая ошибка</p>
          <h1>Букер временно недоступен</h1>
          <p className="timeline">Данные сделки не изменены. Попробуйте открыть сервис ещё раз.</p>
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
