import { PerformerCabinetDashboard } from "@/components/cabinet/performer/PerformerCabinetDashboard";

export const metadata = {
  title: "Кабинет исполнителя",
  robots: { index: false, follow: false },
};

export default function PerformerCabinetPage() {
  return <PerformerCabinetDashboard />;
}
