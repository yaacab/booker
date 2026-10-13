import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  reactStrictMode: true,
  distDir: process.env.BOOKER_E2E_NEXT_DIST_DIR ?? ".next",
  poweredByHeader: false,
  // Keep metadata in <head> and preserve real HTTP 404 statuses for missing
  // public profiles. Streaming not-found responses are otherwise soft 200s.
  htmlLimitedBots: /.*/,
  eslint: { ignoreDuringBuilds: true },
};

export default nextConfig;
