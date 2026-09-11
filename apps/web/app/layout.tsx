import type { Metadata, Viewport } from "next";
import { SiteChrome } from "@/components/SiteChrome";
import "./globals.css";
import "./immersive.css";
import "./cabinet-design.css";
import "./reference-puzzles.css";
import "./workspace-design.css";
import "./reference-interiors.css";
import "./chrome-reference-v2.css";
import "./catalog-reference-v2.css";
import "./deal-reference-v2.css";
import "./workspace-reference-v2.css";
import "./saved-searches-reference-v2.css";
import "./completion-reference.css";
import "./editions.css";
import "./artist-first.css";
import "./black-workspaces.css";

const siteUrl = process.env.NEXT_PUBLIC_SITE_URL || "https://bukergo.ru";

export const metadata: Metadata = {
  metadataBase: new URL(siteUrl),
  title: {
    default: "Букер — работа для артистов и артисты для событий",
    template: "%s · Букер",
  },
  description:
    "Свободные слоты, предложения, подтверждения и документы в одном рабочем пространстве.",
  openGraph: {
    title: "Букер — работа для артистов и артисты для событий",
    description: "Свободные слоты, предложения и подтверждения в одном Deal Room.",
    siteName: "Букер",
    locale: "ru_RU",
    type: "website",
  },
};

export const viewport: Viewport = {
  themeColor: "#edf1eb",
  width: "device-width",
  initialScale: 1,
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="ru" suppressHydrationWarning>
      <head>
        <script dangerouslySetInnerHTML={{__html: `try{document.documentElement.dataset.edition=localStorage.getItem("booker.edition")==="black"?"black":"light"}catch(e){}`}} />
        <link rel="stylesheet" href="/vendor/leaflet/leaflet.css" />
        <link rel="preload" href="/fonts/manrope-cyrillic.woff2" as="font" type="font/woff2" crossOrigin="anonymous" />
        <link rel="preload" href="/fonts/manrope-latin.woff2" as="font" type="font/woff2" crossOrigin="anonymous" />
      </head>
      <body>
        <SiteChrome>{children}</SiteChrome>
      </body>
    </html>
  );
}
