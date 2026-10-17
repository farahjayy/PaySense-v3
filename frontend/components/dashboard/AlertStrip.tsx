"use client";

import Link from "next/link";

import { useAlerts } from "@/lib/api/topic";
import { SEVERITY_COPY } from "@/lib/insights";

/** What needs attention now (WP15 alerts), at the top of the dashboard. Silent when nothing does. */
export function AlertStrip() {
  const alerts = useAlerts();
  if (!alerts.data || alerts.data.items.length === 0) return null;
  return (
    <section
      aria-labelledby="alerts-heading"
      className="rounded-card border border-danger/30 bg-danger-bg px-4 py-3"
    >
      <h2 id="alerts-heading" className="text-[13px] font-semibold text-danger">
        <span aria-hidden>{SEVERITY_COPY.high.glyph} </span>
        Needs your attention
      </h2>
      <ul className="mt-1.5 space-y-1 text-[13px] text-ink">
        {alerts.data.items.map((a) => (
          <li key={`${a.rule}-${a.title}`}>
            <span className="font-semibold">{a.title}.</span>{" "}
            <span className="text-ink-secondary">{a.detail}</span>
          </li>
        ))}
      </ul>
      <Link
        href="/insights"
        className="mt-2 inline-block text-[12px] font-semibold text-accent underline"
      >
        See what to do
      </Link>
    </section>
  );
}
