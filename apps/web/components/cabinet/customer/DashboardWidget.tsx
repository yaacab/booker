import type { ReactNode } from "react";

type DashboardWidgetProps = {
  title: string;
  hint?: string;
  empty?: string;
  isEmpty?: boolean;
  children: ReactNode;
};

export function DashboardWidget({ title, hint, empty, isEmpty, children }: DashboardWidgetProps) {
  return (
    <section className="card dashboard-widget">
      <header className="dashboard-widget-head">
        <h2>{title}</h2>
        {hint ? <p className="timeline">{hint}</p> : null}
      </header>
      {isEmpty ? <p className="timeline">{empty || "Пока пусто"}</p> : children}
    </section>
  );
}
