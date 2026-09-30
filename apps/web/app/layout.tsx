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
import "./login-layout.css";
import "./home-refinement.css";
import "./venue-discovery.css";
import "./artist-welcome.css";

const siteUrl = "https://bukergo.ru";

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
  themeColor: "#101112",
  width: "device-width",
  initialScale: 1,
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="ru" data-edition="black" suppressHydrationWarning>
      <head>
        <style dangerouslySetInnerHTML={{ __html: 'html{background:#101112;color-scheme:dark}html[data-edition="light"]{background:#edf1eb;color-scheme:light}' }} />
        <script dangerouslySetInnerHTML={{ __html: 'try{if(localStorage.getItem("booker.edition")==="light")document.documentElement.dataset.edition="light"}catch(e){};var syncBookerThemeColor=function(){var color=document.documentElement.dataset.edition==="light"?"#edf1eb":"#101112";document.querySelectorAll("meta[name=theme-color]").forEach(function(meta){if(meta.content!==color)meta.content=color})};syncBookerThemeColor();new MutationObserver(syncBookerThemeColor).observe(document.head,{childList:true,subtree:true,attributes:true,attributeFilter:["content"]})' }} />
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
