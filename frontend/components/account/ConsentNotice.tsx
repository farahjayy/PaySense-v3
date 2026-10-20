"use client";

import type { ReactNode } from "react";

import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { ErrorState, Skeleton } from "@/components/ui/States";
import { type Consent, useAcceptConsent, useConsent } from "@/lib/api/topic";

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

/**
 * First login (WP19): the privacy and assistant notice is shown, once per version, before the app.
 * The server enforces it where it matters (the assistant will not call its model provider until
 * the notice is accepted), so if the notice cannot be loaded the app still opens.
 */
export function ConsentGate({ children }: { children: ReactNode }) {
  const consent = useConsent();
  const accept = useAcceptConsent();
  if (consent.isPending) return <Skeleton lines={4} label="Loading" />;
  if (consent.isError || consent.data.accepted) return <>{children}</>;
  return (
    <div className="mx-auto max-w-2xl">
      <Card>
        <h1 tabIndex={-1} className="font-display text-[24px] font-semibold text-ink">
          Before you start
        </h1>
        <p className="mt-1 text-[14px] text-ink-secondary">
          How PaySense handles your data, and what its assistant can and cannot do.
        </p>
        <div className="mt-5">
          <ConsentText consent={consent.data} />
        </div>
        {accept.isError && (
          <div className="mt-4">
            <ErrorState message={accept.error.message} />
          </div>
        )}
        <div className="mt-6 flex flex-wrap gap-2">
          <Button
            variant="accent"
            disabled={accept.isPending}
            onClick={() => accept.mutate(consent.data.version)}
          >
            {accept.isPending ? "Saving…" : "I understand, continue"}
          </Button>
        </div>
      </Card>
    </div>
  );
}
