"use client";

import { useEffect, useId, useState, type ReactNode } from "react";

/**
 * A short hint to the right of a control, on hover or keyboard focus; Escape hides it (WCAG
 * 1.4.13). The control gets the hint as its description through `describedBy`. Fixed-positioned,
 * so a scrolling container (the sidebar's nav) cannot clip it.
 */
export function Tooltip({
  text,
  children,
}: {
  text: string;
  /** An empty `text` renders the control alone, without a hint. */
  children: (describedBy?: string) => ReactNode;
}) {
  const id = useId();
  const [at, setAt] = useState<{ left: number; top: number } | null>(null);
  const show = (event: { currentTarget: HTMLElement }) => {
    const box = event.currentTarget.getBoundingClientRect();
    setAt({ left: box.right + 12, top: box.top + box.height / 2 });
  };
  const hide = () => setAt(null);

  useEffect(() => {
    if (!at) return;
    const onKey = (event: globalThis.KeyboardEvent) => {
      if (event.key === "Escape") setAt(null);
    };
    window.addEventListener("keydown", onKey);
    window.addEventListener("scroll", hide, true);
    return () => {
      window.removeEventListener("keydown", onKey);
      window.removeEventListener("scroll", hide, true);
    };
  }, [at]);

  if (!text) return <>{children()}</>;
  return (
    <div onMouseEnter={show} onMouseLeave={hide} onFocus={show} onBlur={hide}>
      {children(id)}
      {/* Always in the DOM (hidden when closed), so the description is there for screen readers. */}
      <span
        id={id}
        role={at ? "tooltip" : undefined}
        hidden={!at}
        style={at ?? undefined}
        className="tip pointer-events-none fixed z-50 w-max max-w-56 -translate-y-1/2 rounded-xl bg-ink px-3 py-2 text-[12px] font-medium leading-snug text-page shadow-lg before:absolute before:top-1/2 before:-left-1 before:size-2.5 before:-translate-y-1/2 before:rotate-45 before:rounded-[2px] before:bg-ink"
      >
        {text}
      </span>
    </div>
  );
}
