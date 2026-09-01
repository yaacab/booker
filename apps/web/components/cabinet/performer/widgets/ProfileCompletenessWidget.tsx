import { DashboardWidget } from "../../DashboardWidget";
import type { ProfileCompleteness } from "../types";

export function ProfileCompletenessWidget({ completeness }: { completeness: ProfileCompleteness }) {
  const incomplete = completeness.items.filter((item) => !item.done);
  return (
    <DashboardWidget
      title="Профиль"
      hint={`Полнота — ${completeness.score}%`}
      isEmpty={incomplete.length === 0}
      empty="Профиль заполнен полностью."
    >
      <ul className="timeline">
        {incomplete.map((item) => (
          <li key={item.id}>
            ○ {item.label}
          </li>
        ))}
      </ul>
    </DashboardWidget>
  );
}
