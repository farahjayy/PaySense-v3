"use client";

import type { Consent } from "@/lib/api/topic";

/** The notice's sections, as the server wrote them (it names the model provider in use). */
export function ConsentText({ consent }: { consent: Consent }) {
  return (
    <dl className="space-y-3">
      {consent.sections.map((section) => (
        <div key={section.title}>
          <dt className="text-[13px] font-semibold text-ink">{section.title}</dt>
          <dd className="mt-0.5 text-[13px] leading-relaxed text-ink-secondary">{section.text}</dd>
        </div>
      ))}
    </dl>
  );
}
