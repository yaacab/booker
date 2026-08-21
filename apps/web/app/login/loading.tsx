export default function LoginLoading() {
  return (
    <main>
      <p className="kicker">Свои</p>
      <h1>Зайти, пока дата не утекла</h1>
      <div className="skeleton" style={{ minHeight: 180, maxWidth: 420 }} />
    </main>
  );
}
