"use client";

import Link from "next/link";
import { useState, type CSSProperties, type KeyboardEvent, type ReactNode } from "react";

import { BandBadge } from "@/components/ui/BandBadge";
import { Button } from "@/components/ui/Button";
import { Dialog } from "@/components/ui/Dialog";

// One entrance per element, started by a delay; reduced motion shows the finished picture.
const after = (seconds: number): CSSProperties => ({ animationDelay: `${seconds}s` });

/** A forecast line draws in, and the likely range opens out where the future starts. */
function ForecastPicture() {
  return (
    <svg viewBox="0 0 240 120" className="h-full w-full">
      <line x1="10" y1="104" x2="230" y2="104" className="stroke-line" strokeWidth="2" />
      <path
        d="M130 62 L230 30 L230 92 Z"
        className="intro-rise fill-accent-bg"
        style={after(1)}
      />
      <path
        d="M10 80 L40 70 L70 76 L100 58 L130 62 L180 52 L230 60"
        pathLength={1}
        className="intro-draw fill-none stroke-accent"
        strokeWidth="4"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <line x1="130" y1="20" x2="130" y2="104" className="stroke-field" strokeDasharray="4 4" />
    </svg>
  );
}

/** A purchase, then the three answers the check can give. */
function RiskPicture() {
  return (
    <div className="flex h-full flex-col items-center justify-center gap-4">
      <div className="intro-rise w-44 rounded-xl border border-line bg-surface p-3 text-left">
        <p className="text-[13px] font-semibold text-ink">New phone</p>
        <p className="text-[12px] text-ink-muted">Pay later, in instalments</p>
      </div>
      <div className="flex gap-2">
        <span className="intro-pop" style={after(0.5)}>
          <BandBadge band="Safe" />
        </span>
        <span className="intro-pop" style={after(0.7)}>
          <BandBadge band="Caution" />
        </span>
        <span className="intro-pop" style={after(0.9)}>
          <BandBadge band="At Risk" />
        </span>
      </div>
    </div>
  );
}

/** A question, an answer, and a change that waits for Confirm. */
function AssistantPicture() {
  return (
    <div className="flex h-full flex-col justify-center gap-2 px-4 text-[12px]">
      <p className="intro-rise self-end rounded-2xl rounded-br-sm bg-accent px-3 py-1.5 text-on-accent">
        Can I afford a new phone?
      </p>
      <p
        className="intro-rise self-start rounded-2xl rounded-bl-sm border border-line bg-surface px-3 py-1.5 text-ink"
        style={after(0.5)}
      >
        Here is what it does to your next few months.
      </p>
      <div
        className="intro-rise flex items-center justify-between self-start rounded-xl border border-line bg-surface px-3 py-2 text-ink"
        style={after(1)}
      >
        <span className="mr-3">Add this plan?</span>
        <span className="rounded-lg bg-accent px-2 py-0.5 font-semibold text-on-accent">
          Confirm
        </span>
      </div>
    </div>
  );
}

/** What the person can always do with their data. */
function DataPicture() {
  const rows = ["Download everything", "Delete everything", "Assistant asks first"];
  return (
    <ul className="flex h-full flex-col justify-center gap-2 px-6 text-[13px] text-ink">
      {rows.map((row, i) => (
        <li
          key={row}
          className="intro-rise flex items-center gap-2 rounded-xl border border-line bg-surface px-3 py-2"
          style={after(0.3 * i)}
        >
          <span className="flex h-5 w-5 items-center justify-center rounded-full bg-accent text-[11px] text-on-accent">
            ✓
          </span>
          {row}
        </li>
      ))}
    </ul>
  );
}

const SLIDES: readonly { title: string; body: string; picture: ReactNode }[] = [
  {
    title: "See where your money is heading",
    body: "PaySense plays your next few months forward from your own spending, income and bills, and shows how likely you are to stay above zero.",
    picture: <ForecastPicture />,
  },
  {
    title: "Check a pay-later buy before you commit",
    body: "Describe a purchase and a provider. You get Safe, Caution or At Risk, and the reasons, worked out from your own figures. Nothing is saved until you add it.",
    picture: <RiskPicture />,
  },
  {
    title: "Ask PaySense",
    body: "Ask in your own words. It explains and suggests, and nothing in your data changes until you press Confirm.",
    picture: <AssistantPicture />,
  },
  {
    title: "Your data stays yours",
    body: "Download or delete everything at any time, under Your data. The assistant asks for your consent before it uses any of your figures.",
    picture: <DataPicture />,
  },
];

/** What PaySense is, in four slides: shown once per browser after sign-in, and on request. */
export function IntroTour({ onClose }: { onClose: () => void }) {
  const [step, setStep] = useState(0);
  const last = step === SLIDES.length - 1;
  const slide = SLIDES[step];
  const go = (to: number) => setStep(Math.min(Math.max(to, 0), SLIDES.length - 1));

  function onKeyDown(event: KeyboardEvent) {
    if (event.key === "ArrowRight") go(step + 1);
    if (event.key === "ArrowLeft") go(step - 1);
  }

  return (
    <Dialog open title="Welcome to PaySense" onClose={onClose}>
      <div onKeyDown={onKeyDown}>
        {/* Keyed by step, so each slide's picture plays its entrance when it arrives. */}
        <div key={step}>
          <div aria-hidden className="h-40 overflow-hidden rounded-xl bg-surface-2">
            {slide.picture}
          </div>
          <div aria-live="polite" className="mt-4">
            <p className="sr-only">
              Step {step + 1} of {SLIDES.length}
            </p>
            <h3 className="font-display text-[20px] font-bold leading-snug text-ink">
              {slide.title}
            </h3>
            <p className="mt-1.5 text-[14px] leading-relaxed text-ink-secondary">{slide.body}</p>
          </div>
        </div>
        <div className="mt-5 flex items-center justify-between gap-3">
          <div aria-hidden className="flex gap-1.5">
            {SLIDES.map((s, i) => (
              <span
                key={s.title}
                className={`h-2 rounded-full transition-all ${i === step ? "w-5 bg-accent" : "w-2 bg-line"}`}
              />
            ))}
          </div>
          <div className="flex flex-wrap items-center justify-end gap-2">
            {!last && (
              <button
                type="button"
                onClick={onClose}
                className="rounded-xl px-3 py-1.5 text-[13px] font-semibold text-ink-secondary hover:text-ink"
              >
                Skip
              </button>
            )}
            {step > 0 && (
              <Button variant="secondary" size="sm" onClick={() => go(step - 1)}>
                Back
              </Button>
            )}
            {last ? (
              <>
                <Link
                  href="/import"
                  onClick={onClose}
                  className="rounded-xl px-3 py-1.5 text-[13px] font-semibold text-accent hover:underline"
                >
                  Import a statement
                </Link>
                <Button variant="accent" size="sm" onClick={onClose}>
                  Look around
                </Button>
              </>
            ) : (
              <Button variant="accent" size="sm" onClick={() => go(step + 1)}>
                Next
              </Button>
            )}
          </div>
        </div>
      </div>
    </Dialog>
  );
}
