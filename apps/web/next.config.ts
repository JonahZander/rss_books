import type { NextConfig } from "next";

// Production is a static export served same-origin by the FastAPI process
// (set STATIC_EXPORT=1 at build time). In `next dev` the rewrites below
// proxy API traffic to the backend, so the app is same-origin there too -
// no CORS anywhere.
const nextConfig: NextConfig = {
  reactStrictMode: true,
  output: process.env.STATIC_EXPORT ? "export" : undefined,
  images: { unoptimized: true },
  async rewrites() {
    const api = process.env.DEV_API_ORIGIN ?? "http://localhost:8765";
    return [
      { source: "/api/:path*", destination: `${api}/api/:path*` },
      { source: "/opds", destination: `${api}/opds` },
      { source: "/opds/:path*", destination: `${api}/opds/:path*` },
      { source: "/health", destination: `${api}/health` },
    ];
  },
};

export default nextConfig;
