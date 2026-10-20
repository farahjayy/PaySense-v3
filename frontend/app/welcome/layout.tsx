import type { ReactNode } from "react";

// The welcome page shares the login page's look (soft pond theme, the band characters).
import "../login/login.css";
import "./welcome.css";

export default function WelcomeLayout({ children }: { children: ReactNode }) {
  return <div className="login-theme">{children}</div>;
}
