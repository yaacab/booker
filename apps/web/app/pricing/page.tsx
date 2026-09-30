import type { Metadata } from "next";
import { PricingClient } from "@/components/commerce/PricingClient";

export const metadata: Metadata = {
  title: "Тарифы для исполнителей, площадок и организаторов",
  description: "Выберите инструменты для событий: Free, Pro, Premium и Business. Прозрачные комиссии, календарь и сделки в Букере.",
  alternates: { canonical: "https://bukergo.ru/pricing" },
  openGraph: { title: "Тарифы · Букер", url: "https://bukergo.ru/pricing" },
};
export default function PricingPage() { return <PricingClient />; }
