import { CabinetDashboard } from "@/components/cabinet/CabinetDashboard";

export const metadata = {
  title: "Кабинет исполнителя",
  robots: { index: false, follow: false },
};

export default function PerformerCabinetPage() {
  return <CabinetDashboard cabinetMode="performer" />;
}
