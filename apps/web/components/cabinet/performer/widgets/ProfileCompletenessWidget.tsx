import { DashboardWidget } from "../../DashboardWidget";
import type { ProfileCompleteness } from "../types";

export function ProfileCompletenessWidget({ completeness }: { completeness: ProfileCompleteness }) {
  const incomplete = completeness.items.filter((item) => !item.done);
  return (
    <DashboardWidget
      title="Профиль"
      hint={incomplete.length ? `${incomplete.length} пункта к заполнению` : "Готово к выдаче"}
    >
      <div className="workspace-profile-score"><span>Профиль заполнен на</span><strong>{completeness.score}%</strong><progress max={100} value={completeness.score} aria-label="Полнота профиля" /></div>
      <ul className="timeline">
        {completeness.items.map((item) => (
          <li key={item.id}>
            <span className={item.done ? "workspace-check done" : "workspace-check"}>{item.done ? "✓" : "○"}</span> {item.label}
          </li>
        ))}
      </ul>
    </DashboardWidget>
  );
}
