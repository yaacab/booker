import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  reactStrictMode: true,
  eslint: { ignoreDuringBuilds: true },
  // Demo cabinets only on dev/stage builds; production inlines "0" so the links are stripped from bundles.
  env: { NEXT_PUBLIC_DEMO_CABINETS: process.env.NEXT_PUBLIC_DEMO_CABINETS === "1" ? "1" : "0" },
};

export default nextConfig;
