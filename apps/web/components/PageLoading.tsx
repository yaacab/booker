export function PageLoading({ title, label = "Загружаем страницу", cards = 2 }: { title: string; label?: string; cards?: number }) {
  return <main className="reference-loading" aria-busy="true" aria-label={label}>
    <p className="kicker" role="status">{label}…</p><h1>{title}</h1>
    <div className="loading-cards" aria-hidden="true">{Array.from({ length: cards }, (_, i) => <div className="skeleton" key={i} />)}</div>
  </main>;
}
