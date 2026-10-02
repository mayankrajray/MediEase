import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Self-contained server bundle for the web Docker image (M0-P5).
  output: "standalone",
  // Do not advertise the framework in response headers.
  poweredByHeader: false,
  reactStrictMode: true,
};

export default nextConfig;
