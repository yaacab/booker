export function BrandLockup({ compact = false }: { compact?: boolean }) {
  return (
    <span className={`brand-lockup ${compact ? "compact" : ""}`}>
      <span className="brand-word">Букер<span className="brand-lime-dot" aria-hidden="true">•</span></span>
    </span>
  );
}
