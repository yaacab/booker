import { PerformerCabinetDashboard } from "@/components/cabinet/performer/PerformerCabinetDashboard";

export const metadata = {
  title: "Заявки исполнителя",
  robots: { index: false, follow: false },
};

export default function PerformerRequestsPage() {
  return <PerformerCabinetDashboard section="requests" />;
}
