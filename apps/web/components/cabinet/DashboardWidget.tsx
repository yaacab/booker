import type { ReactNode } from "react";
import { cabinetWidgetHeadingId } from "@/lib/cabinetA11y";

type DashboardWidgetProps = {
  title: string;
  hint?: string;
  empty?: string;
  isEmpty?: boolean;
  children: ReactNode;
};

export function DashboardWidget({ title, hint, empty, isEmpty, children }: DashboardWidgetProps) {
  const headingId = cabinetWidgetHeadingId(title);

  return (
    <section className="card dashboard-widget" aria-labelledby={headingId}>
      <header className="dashboard-widget-head">
        <h2 id={headingId}>{title}</h2>
        {hint ? <p className="timeline">{hint}</p> : null}
      </header>
      {isEmpty ? <p className="timeline">{empty || "Пока пусто"}</p> : children}
    </section>
  );
}
