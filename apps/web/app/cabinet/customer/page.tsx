import { CabinetDashboard } from "@/components/cabinet/CabinetDashboard";

export const metadata = {
  title: "Кабинет заказчика",
  robots: { index: false, follow: false },
};

export default function CustomerCabinetPage() {
  return <CabinetDashboard cabinetMode="customer" />;
}
