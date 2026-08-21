import type { Metadata, Viewport } from "next";
import { SiteChrome } from "@/components/SiteChrome";
import "./globals.css";

const siteUrl = process.env.NEXT_PUBLIC_SITE_URL || "https://bukergo.ru";

export const metadata: Metadata = {
  metadataBase: new URL(siteUrl),
  title: {
    default: "Букер — пока вы спорите в чате, дата уже чужая",
    template: "%s · Букер",
  },
  description:
    "Слот, цифра с сервера и подписи в одной комнате. Мы не играем сет и не сдаём зал. Спор разбирает человек.",
  openGraph: {
    title: "Букер — пока вы спорите в чате, дата уже чужая",
    description: "Слот, цифра с сервера и подписи в одной комнате.",
    siteName: "Букер",
    locale: "ru_RU",
    type: "website",
  },
};

export const viewport: Viewport = {
  themeColor: "#2D6A66",
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
