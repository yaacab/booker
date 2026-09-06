import { VenueCabinetDashboard } from "@/components/cabinet/venue/VenueCabinetDashboard";

export const metadata = {
  title: "Календарь площадки",
  robots: { index: false, follow: false },
};

export default function VenueCalendarPage() {
  return <VenueCabinetDashboard section="calendar" />;
}
