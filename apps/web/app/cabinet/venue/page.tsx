import { VenueCabinetDashboard } from "@/components/cabinet/venue/VenueCabinetDashboard";

export const metadata = {
  title: "Кабинет площадки",
  robots: { index: false, follow: false },
};

export default function VenueCabinetPage() {
  return <VenueCabinetDashboard />;
}
