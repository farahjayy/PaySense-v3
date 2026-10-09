import type { NextConfig } from "next";

// Headers that are safe for every route. The Content-Security-Policy is not here: it carries a
// per-request script nonce, so `proxy.ts` sets it (policy text in `lib/csp.ts`).
const SECURITY_HEADERS = [
  { key: "X-Frame-Options", value: "DENY" },
  { key: "X-Content-Type-Options", value: "nosniff" },
  { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
  { key: "Permissions-Policy", value: "camera=(), microphone=(), geolocation=()" },
  { key: "Strict-Transport-Security", value: "max-age=31536000; includeSubDomains" },
];

// cacheComponents / partialPrefetching are deliberately off: every screen is per-user data fetched
// in the browser with a bearer token held in sessionStorage, so there is nothing to cache on the
// server, and hidden-route <Activity> retention would only complicate auth redirects.
const nextConfig: NextConfig = {
  // The e2e run sets NEXT_DIST_DIR so it never fights a developer's `next dev` over `.next/dev/lock`.
  distDir: process.env.NEXT_DIST_DIR ?? ".next",
  async headers() {
    return [{ source: "/:path*", headers: SECURITY_HEADERS }];
  },
  turbopack: {
    rules: {
      "*.css": {
        loaders: ["@tailwindcss/turbopack"],
        as: "*.css",
      },
    },
  },
};

export default nextConfig;
