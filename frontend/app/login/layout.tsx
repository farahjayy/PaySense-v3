import type { ReactNode } from "react";

import "./login.css";

// The brand fonts are loaded once in the root layout (`--font-brand-display`, `--font-brand-body`).
export default function LoginLayout({ children }: { children: ReactNode }) {
  return <div className="login-theme">{children}</div>;
}
