export function BrandLockup({ compact = false }: { compact?: boolean }) {
  return (
    <span className={`brand-lockup ${compact ? "compact" : ""}`}>
      <img src="/mark.svg" alt="" width={compact ? 22 : 32} height={compact ? 22 : 32} />
      <span className="brand-word">Букер</span>
    </span>
  );
}
