import { VenueCabinetDashboard } from "@/components/cabinet/venue/VenueCabinetDashboard";

export const metadata = {
  title: "Статистика площадки",
  robots: { index: false, follow: false },
};

export default function VenueStatsPage() {
  return <VenueCabinetDashboard section="stats" />;
}
