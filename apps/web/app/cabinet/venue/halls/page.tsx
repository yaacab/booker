import { VenueCabinetDashboard } from "@/components/cabinet/venue/VenueCabinetDashboard";

export const metadata = {
  title: "Залы площадки",
  robots: { index: false, follow: false },
};

export default function VenueHallsPage() {
  return <VenueCabinetDashboard section="halls" />;
}
