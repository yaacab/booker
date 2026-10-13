import type { Metadata } from "next";

export const metadata: Metadata = {
  title: "Вход через Telegram · Букер",
  robots: { index: false, follow: false },
};

export default function TelegramLayout({ children }: { children: React.ReactNode }) {
  return children;
}
