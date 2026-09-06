import { PerformerCabinetDashboard } from "@/components/cabinet/performer/PerformerCabinetDashboard";

export const metadata = {
  title: "Календарь исполнителя",
  robots: { index: false, follow: false },
};

export default function PerformerCalendarPage() {
  return <PerformerCabinetDashboard section="calendar" />;
}
