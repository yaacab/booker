import type { MetadataRoute } from "next";
import { canonicalSiteUrl } from "@/lib/seo";

export default function robots(): MetadataRoute.Robots {
  const base = canonicalSiteUrl();
  return {
    rules: [
      {
        userAgent: "*",
        allow: "/",
        disallow: [
          "/cabinet",
          "/admin",
          "/profile",
          "/login",
          "/events/",
          "/deals/",
          "/briefs",
          "/compare",
          "/support",
          "/investor",
          "/s/",
          "/api/",
        ],
      },
      { userAgent: "GPTBot", allow: "/" },
      { userAgent: "ChatGPT-User", allow: "/" },
      { userAgent: "OAI-SearchBot", allow: "/" },
    ],
    sitemap: `${base}/sitemap.xml`,
    host: base,
  };
}
