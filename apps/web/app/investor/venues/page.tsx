import type { Metadata } from "next";
import InvestorVenuesPrivate from "@/components/InvestorVenuesPrivate";

export const metadata: Metadata = {
  title: "Исследовательские площадки — Букер",
  description: "Закрытая исследовательская витрина для администратора Букера.",
  robots: { index: false, follow: false },
};

export default function InvestorVenuesPage() {
  return <InvestorVenuesPrivate />;
}
