import { CabinetDashboard } from "@/components/cabinet/CabinetDashboard";

export const metadata = {
  title: "Кабинет площадки",
  robots: { index: false, follow: false },
};

export default function VenueCabinetPage() {
  return <CabinetDashboard cabinetMode="venue" />;
}
