import { Bricolage_Grotesque, Figtree } from "next/font/google";
import type { ReactNode } from "react";

import "./login.css";

// The two fonts are used on the login page only (self-hosted by Next, so `font-src 'self'` holds).
const display = Bricolage_Grotesque({
  subsets: ["latin"],
  variable: "--font-login-display",
  display: "swap",
});
const body = Figtree({ subsets: ["latin"], variable: "--font-login-body", display: "swap" });

export default function LoginLayout({ children }: { children: ReactNode }) {
  return <div className={`login-theme ${display.variable} ${body.variable}`}>{children}</div>;
}
