"use client";

import Link from "next/link";
import { useState, useSyncExternalStore } from "react";

import { Button } from "@/components/ui/Button";
import { Card, CardCaption, CardTitle } from "@/components/ui/Card";
import {
  useForecast,
  usePlans,
  useProviderLimits,
  useRecurringItems,
} from "@/lib/api/queries";
import { gettingStartedSteps } from "@/lib/onboarding";

const HIDDEN_KEY = "paysense.gettingStarted.hidden";

/**
 * The route from an empty app to a first risk check, ticking itself off from what the person has
 * actually done. It shows nothing while it is unsure (loading, or a failed call) and goes away when
 * every step is done, so it never shows a wrong checklist or nags a finished student. A student who
 * will never do every step (no BNPL, so no limits and no plans) can hide it; the choice is kept in
 * this browser only.
 */
const subscribers = new Set<() => void>();

function subscribe(notify: () => void): () => void {
  subscribers.add(notify);
  window.addEventListener("storage", notify);
  return () => {
    subscribers.delete(notify);
    window.removeEventListener("storage", notify);
  };
}

function storedHidden(): boolean {
  try {
    return window.localStorage.getItem(HIDDEN_KEY) === "1";
  } catch {
    return false; // storage can be blocked (private window): the checklist simply stays
  }
}

export function GettingStarted() {
  const stored = useSyncExternalStore(subscribe, storedHidden, () => false);
  const [hiddenNow, setHiddenNow] = useState(false); // covers a browser that will not store it
  const hidden = stored || hiddenNow;
  function hide() {
    setHiddenNow(true);
    try {
      window.localStorage.setItem(HIDDEN_KEY, "1");
      subscribers.forEach((notify) => notify());
    } catch {
      // not kept, but hidden for this visit
    }
  }
  const forecast = useForecast();
  const recurring = useRecurringItems();
  const limits = useProviderLimits();
  const plans = usePlans();

  if (hidden || !forecast.data || !recurring.data || !limits.data || !plans.data) {
    return null;
  }
  const steps = gettingStartedSteps({
    monthsOfHistory: forecast.data.months_of_history,
    recurringCount: recurring.data.length,
    limitsRecorded: limits.data.filter((l) => l.limit_sen !== null).length,
    forecastReady: forecast.data.status === "ok",
    riskChecked: plans.data.some((p) => p.risk_score_at_creation !== null),
  });
  const done = steps.filter((s) => s.done).length;
  if (done === steps.length) return null;

  return (
    <Card>
      <div className="flex items-start justify-between gap-3">
        <div>
          <CardTitle>Getting started</CardTitle>
          <CardCaption>
            {done} of {steps.length} done
          </CardCaption>
        </div>
        <Button variant="secondary" size="sm" onClick={hide}>
          Hide this
        </Button>
      </div>
      <ol aria-label="Getting started steps" className="mt-4 space-y-3.5">
        {steps.map((step) => (
          <li key={step.id} className="flex gap-3">
            <span
              aria-hidden
              className={`mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full border text-[11px] font-bold ${
                step.done
                  ? "border-success bg-success-bg text-success"
                  : "border-field bg-surface text-ink-muted"
              }`}
            >
              {step.done ? "✓" : ""}
            </span>
            <span className="sr-only">{step.done ? "Done" : "To do"}</span>
            <div className="min-w-0 flex-1">
              <p
                className={`text-[14px] font-medium ${step.done ? "text-ink-secondary" : "text-ink"}`}
              >
                {step.title}
                {step.detail && (
                  <span className="ml-2 text-[12px] font-normal text-ink-secondary">
                    {step.detail}
                  </span>
                )}
              </p>
              {!step.done && (
                <>
                  <p className="mt-0.5 text-[13px] leading-relaxed text-ink-secondary">
                    {step.why}
                  </p>
                  {step.href && (
                    <Link
                      href={step.href}
                      className="mt-1 inline-block text-[13px] font-semibold text-accent underline-offset-2 hover:underline"
                    >
                      {step.action ?? "Open"}
                    </Link>
                  )}
                </>
              )}
            </div>
          </li>
        ))}
      </ol>
    </Card>
  );
}
