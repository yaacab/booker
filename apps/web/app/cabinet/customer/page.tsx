import { CustomerCabinetDashboard } from "@/components/cabinet/customer/CustomerCabinetDashboard";

export const metadata = {
  title: "Кабинет заказчика",
  robots: { index: false, follow: false },
};

export default function CustomerCabinetPage() {
  return <CustomerCabinetDashboard />;
}
