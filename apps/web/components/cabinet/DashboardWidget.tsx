import type { ReactNode } from "react";
import { cabinetWidgetHeadingId } from "@/lib/cabinetA11y";

type DashboardWidgetProps = {
  title: string;
  hint?: string;
  empty?: string;
  isEmpty?: boolean;
  children: ReactNode;
  span?: "full" | "half";
  accent?: "venue" | "performer" | "customer" | "neutral";
};

export function DashboardWidget({
  title,
  hint,
  empty,
  isEmpty,
  children,
  span = "half",
  accent = "neutral",
}: DashboardWidgetProps) {
  const headingId = cabinetWidgetHeadingId(title);

  return (
    <section
      className={`card dashboard-widget span-${span} accent-${accent}`}
      aria-labelledby={headingId}
    >
      <header className="dashboard-widget-head">
        <h2 id={headingId}>{title}</h2>
        {hint ? <p className="timeline">{hint}</p> : null}
      </header>
      {isEmpty ? <p className="timeline dashboard-empty">{empty || "Пока пусто"}</p> : children}
    </section>
  );
}
