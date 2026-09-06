import { VenueCabinetDashboard } from "@/components/cabinet/venue/VenueCabinetDashboard";

export const metadata = {
  title: "Заявки площадки",
  robots: { index: false, follow: false },
};

export default function VenueRequestsPage() {
  return <VenueCabinetDashboard section="requests" />;
}
