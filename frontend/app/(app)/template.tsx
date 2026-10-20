import type { ReactNode } from "react";

// A template remounts on every navigation (a layout does not), so each page plays its entrance.
export default function PageTransition({ children }: { children: ReactNode }) {
  return <div className="page-enter">{children}</div>;
}
