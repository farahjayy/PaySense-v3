import type { NextConfig } from "next";

// cacheComponents / partialPrefetching are deliberately off: every screen is per-user data fetched
// in the browser with a bearer token held in sessionStorage, so there is nothing to cache on the
// server, and hidden-route <Activity> retention would only complicate auth redirects.
const nextConfig: NextConfig = {
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
