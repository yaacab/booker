'use client';
export default function ErrorPage({ reset }: { reset: () => void }) { return <main className="commerce-page"><h1>Подборки временно недоступны</h1><p role="alert">Не удалось загрузить каталог. Попробуйте ещё раз.</p><button className="btn" onClick={reset}>Повторить загрузку</button></main>; }
