import { PerformerCabinetDashboard } from "@/components/cabinet/performer/PerformerCabinetDashboard";

export const metadata = {
  title: "Услуги исполнителя",
  robots: { index: false, follow: false },
};

export default function PerformerServicesPage() {
  return <PerformerCabinetDashboard section="services" />;
}
