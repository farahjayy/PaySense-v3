import type { NextConfig } from "next";

// Headers that are safe for every route. A full script-src / connect-src Content-Security-Policy
// needs per-request nonces for Next's inline hydration scripts; it is planned for P8 (deployment)
// together with the real API origin. Until then this blocks framing, plugin content, base-tag
// injection and MIME sniffing.
const SECURITY_HEADERS = [
  {
    key: "Content-Security-Policy",
    value: "frame-ancestors 'none'; base-uri 'self'; object-src 'none'; form-action 'self'",
  },
  { key: "X-Frame-Options", value: "DENY" },
  { key: "X-Content-Type-Options", value: "nosniff" },
  { key: "Referrer-Policy", value: "strict-origin-when-cross-origin" },
  { key: "Permissions-Policy", value: "camera=(), microphone=(), geolocation=()" },
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
