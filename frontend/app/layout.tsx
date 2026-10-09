import type { Metadata, Viewport } from "next";
import { connection } from "next/server";
import type { ReactNode } from "react";

import { Providers } from "./providers";
import "./globals.css";

export const metadata: Metadata = {
  title: { default: "PaySense", template: "%s · PaySense" },
  description:
    "Financial health forecasting and BNPL risk classification for Malaysian university students.",
};

export const viewport: Viewport = { width: "device-width", initialScale: 1 };

// Every page is rendered per request: the Content-Security-Policy in `proxy.ts` carries a fresh
// script nonce, and Next can only stamp a nonce on a page that is rendered after the request.
export default async function RootLayout({ children }: { children: ReactNode }) {
  await connection();
  return (
    <html lang="en" className="h-full antialiased">
      <body className="min-h-full">
        <Providers>{children}</Providers>
      </body>
    </html>
  );
}
