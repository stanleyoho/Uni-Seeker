import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Allow accessing the dev server from 127.0.0.1 in addition to localhost.
  // Without this, dev-only assets (HMR scripts, React Server Component
  // payloads) are blocked when the browser address is 127.0.0.1:3001,
  // leaving the page shell rendered but the client tree stuck mid-hydration
  // — symptom: home page spins forever.
  allowedDevOrigins: ["127.0.0.1"],
};

export default nextConfig;
