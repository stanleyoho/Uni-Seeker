import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  // Allow accessing the dev server from 127.0.0.1 in addition to localhost.
  // Without this, dev-only assets (HMR scripts, React Server Component
  // payloads) are blocked when the browser address is 127.0.0.1:3001,
  // leaving the page shell rendered but the client tree stuck mid-hydration
  // — symptom: home page spins forever.
  allowedDevOrigins: ["127.0.0.1"],

  // Tree-shake barrel-export libs. `lucide-react` and `recharts` both
  // re-export hundreds of components from their package index; without
  // this flag, importing a single icon or chart pulls the entire
  // library into the page's client chunk. The TanStack libs benefit
  // because their ESM exports include dev-only helpers.
  // Ref: node_modules/next/dist/docs/01-app/03-api-reference/05-config/
  //      01-next-config-js/optimizePackageImports.mdx
  experimental: {
    optimizePackageImports: [
      "lucide-react",
      "recharts",
      "@tanstack/react-query",
      "@tanstack/react-virtual",
    ],
  },

  // No external image hosts in current code (grep for `next/image`
  // confirms zero usages). Leave images config at defaults; add
  // `images.remotePatterns` here once we start pulling logos / charts
  // from upstream CDNs (e.g. finmind, fmp, polygon).
};

export default nextConfig;
