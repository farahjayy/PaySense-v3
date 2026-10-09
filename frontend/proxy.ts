import { NextResponse, type NextRequest } from "next/server";

import { apiOrigin, buildCsp, newNonce } from "@/lib/csp";

/** Gives every page request its own script nonce and the matching Content-Security-Policy. */
export function proxy(request: NextRequest) {
  const isDev = process.env.NODE_ENV === "development";
  const nonce = newNonce();
  const policy = buildCsp({
    nonce,
    apiOrigin: apiOrigin(process.env.NEXT_PUBLIC_API_BASE_URL, isDev),
    isDev,
  });

  // Next reads the nonce from the request's policy header while rendering and stamps it on its own
  // scripts; the response header is what the browser enforces.
  const headers = new Headers(request.headers);
  headers.set("x-nonce", nonce);
  headers.set("Content-Security-Policy", policy);

  const response = NextResponse.next({ request: { headers } });
  response.headers.set("Content-Security-Policy", policy);
  return response;
}

export const config = {
  matcher: [
    {
      source: "/((?!api/|_next/static|_next/image|favicon.ico).*)",
      missing: [
        { type: "header", key: "next-router-prefetch" },
        { type: "header", key: "purpose", value: "prefetch" },
      ],
    },
  ],
};
