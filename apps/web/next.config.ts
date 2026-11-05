import type { NextConfig } from "next";

const apiProxyTarget =
  process.env.BOOKER_INTERNAL_API_URL ||
  process.env.NEXT_PUBLIC_API_URL ||
  "http://127.0.0.1:8000";

const nextConfig: NextConfig = {
  reactStrictMode: true,
  poweredByHeader: false,
  eslint: { ignoreDuringBuilds: true },
  // Demo cabinets only on dev/stage builds; production inlines "0" so the links are stripped from bundles.
  env: { NEXT_PUBLIC_DEMO_CABINETS: process.env.NEXT_PUBLIC_DEMO_CABINETS === "1" ? "1" : "0" },
  // Local preview: browser calls `/api/*` — proxy to the FastAPI process.
  async rewrites() {
    const base = apiProxyTarget.replace(/\/$/, "");
    return [{ source: "/api/:path*", destination: `${base}/:path*` }];
  },
};

export default nextConfig;
