import type { Metadata, Viewport } from "next";
import { SiteChrome } from "@/components/SiteChrome";
import "./globals.css";
import "./immersive.css";
import "./cabinet-design.css";
import "./reference-v3.css";
import "./profile-v3.css";

const siteUrl = process.env.NEXT_PUBLIC_SITE_URL || "https://bukergo.ru";

export const metadata: Metadata = {
  metadataBase: new URL(siteUrl),
  title: {
    default: "Букер — сделки с артистами и площадками",
    template: "%s · Букер",
  },
  description:
    "Свободные слоты, предложения, подтверждения и документы в одном рабочем пространстве.",
  openGraph: {
    title: "Букер — сделки с артистами и площадками",
    description: "Свободные слоты, предложения и подтверждения в одном Deal Room.",
    siteName: "Букер",
    locale: "ru_RU",
    type: "website",
  },
};

export const viewport: Viewport = {
  themeColor: "#f4f7f2",
  width: "device-width",
  initialScale: 1,
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="ru">
      <head>
        <link rel="preload" href="/fonts/manrope-cyrillic.woff2" as="font" type="font/woff2" crossOrigin="anonymous" />
        <link rel="preload" href="/fonts/manrope-latin.woff2" as="font" type="font/woff2" crossOrigin="anonymous" />
      </head>
      <body>
        <SiteChrome>{children}</SiteChrome>
      </body>
    </html>
  );
}
