export default function SearchLoading() {
  return (
    <main>
      <p className="kicker">Только те, у кого дата в календаре. Остальные просто красивые.</p>
      <h1>Кто ещё не занят</h1>
      <div className="catalog-layout">
        <div className="skeleton" style={{ minHeight: 180 }} />
        <div className="grid">
          <div className="skeleton" />
          <div className="skeleton" />
          <div className="skeleton" />
        </div>
      </div>
    </main>
  );
}
