"use client";

import Link from "next/link";
import {
  useEffect,
  useRef,
  useState,
  type CSSProperties,
  type KeyboardEvent,
  type ReactNode,
} from "react";

import { ConsentText } from "@/components/account/ConsentNotice";
import { BrandMark } from "@/components/auth/LoginArt";
import { BandBadge } from "@/components/ui/BandBadge";
import { Button } from "@/components/ui/Button";
import { ErrorState, Skeleton } from "@/components/ui/States";
import { type Consent, useAcceptConsent, useConsent } from "@/lib/api/topic";
import { introSeen, markIntroSeen } from "@/lib/introTour";

// One entrance per element, started by a delay; reduced motion shows the finished picture.
const after = (seconds: number): CSSProperties => ({ animationDelay: `${seconds}s` });

/** A forecast line draws in, and the likely range opens out where the future starts. */
function ForecastPicture() {
  return (
    <svg viewBox="0 0 240 150" className="h-full w-full">
      <line x1="10" y1="130" x2="230" y2="130" className="stroke-line" strokeWidth="2" />
      <path d="M130 78 L230 36 L230 116 Z" className="intro-rise fill-accent-bg" style={after(1)} />
      <path
        d="M10 100 L40 88 L70 95 L100 72 L130 78 L180 66 L230 76"
        pathLength={1}
        className="intro-draw fill-none stroke-accent"
        strokeWidth="4"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
      <line x1="130" y1="20" x2="130" y2="130" className="stroke-field" strokeDasharray="4 4" />
      <circle cx="130" cy="78" r="6" className="intro-pop fill-rose" style={after(0.9)} />
    </svg>
  );
}

/** A purchase, then the three answers the check can give. */
function RiskPicture() {
  return (
    <div className="flex h-full flex-col items-center justify-center gap-5">
      <div className="intro-rise w-52 rounded-2xl border border-line bg-surface p-4 text-left shadow-sm">
        <p className="text-[14px] font-semibold text-ink">New phone</p>
        <p className="text-[13px] text-ink-muted">Pay later, in instalments</p>
      </div>
      <div className="flex gap-2">
        {(["Safe", "Caution", "At Risk"] as const).map((band, i) => (
          <span key={band} className="intro-pop" style={after(0.5 + 0.2 * i)}>
            <BandBadge band={band} />
          </span>
        ))}
      </div>
    </div>
  );
}

/** A question, an answer, and a change that waits for Confirm. */
function AssistantPicture() {
  return (
    <div className="flex h-full flex-col justify-center gap-2.5 px-2 text-[13px]">
      <p className="intro-rise self-end rounded-2xl rounded-br-sm bg-accent px-3 py-2 text-on-accent">
        Can I afford a new phone?
      </p>
      <p
        className="intro-rise self-start rounded-2xl rounded-bl-sm border border-line bg-surface-2 px-3 py-2 text-ink"
        style={after(0.5)}
      >
        Here is what it does to your next few months.
      </p>
      <div
        className="intro-rise flex items-center justify-between self-start rounded-xl border border-line bg-surface px-3 py-2 text-ink shadow-sm"
        style={after(1)}
      >
        <span className="mr-3">Add this plan?</span>
        <span className="intro-pop rounded-lg bg-accent px-2.5 py-1 font-semibold text-on-accent" style={after(1.4)}>
          Confirm
        </span>
      </div>
    </div>
  );
}

/** A tick list, one row at a time. */
function TickPicture({ rows }: { rows: readonly string[] }) {
  return (
    <ul className="flex h-full flex-col justify-center gap-2.5 px-2 text-[14px] text-ink">
      {rows.map((row, i) => (
        <li
          key={row}
          className="intro-rise flex items-center gap-2.5 rounded-xl border border-line bg-surface px-3 py-2.5 shadow-sm"
          style={after(0.3 * i)}
        >
          <span
            className="intro-pop flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-accent text-[12px] text-on-accent"
            style={after(0.3 * i + 0.25)}
          >
            ✓
          </span>
          {row}
        </li>
      ))}
    </ul>
  );
}

/** A shield draws itself, for the privacy notice. */
function NoticePicture() {
  return (
    <svg viewBox="0 0 240 150" className="h-full w-full">
      <path
        d="M120 18 L170 36 V76 C170 104 148 124 120 134 C92 124 70 104 70 76 V36 Z"
        className="intro-rise fill-accent-bg"
        style={after(0.2)}
      />
      <path
        d="M120 18 L170 36 V76 C170 104 148 124 120 134 C92 124 70 104 70 76 V36 Z"
        pathLength={1}
        className="intro-draw fill-none stroke-accent"
        strokeWidth="4"
        strokeLinejoin="round"
      />
      <path
        d="M100 76 L114 90 L142 62"
        pathLength={1}
        className="intro-draw fill-none stroke-accent"
        style={after(0.9)}
        strokeWidth="6"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

/** A tick in a ring, with a small burst around it. */
function FinishPicture() {
  const dots = Array.from({ length: 8 }, (_, i) => (i * Math.PI) / 4);
  return (
    <svg viewBox="0 0 240 150" className="h-full w-full">
      {dots.map((angle, i) => (
        <circle
          key={angle}
          cx={120 + Math.cos(angle) * 62}
          cy={75 + Math.sin(angle) * 62}
          r="5"
          className={`intro-pop ${i % 2 ? "fill-rose" : "fill-accent-soft"}`}
          style={after(0.8 + 0.05 * i)}
        />
      ))}
      <circle cx="120" cy="75" r="42" className="intro-pop fill-accent" />
      <path
        d="M100 76 L114 90 L142 62"
        pathLength={1}
        className="intro-draw fill-none stroke-on-accent"
        style={after(0.4)}
        strokeWidth="7"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  );
}

type Step = { kind: "slide" | "notice" | "finish"; title: string; body: string; picture: ReactNode };

const SLIDES: readonly Step[] = [
  {
    kind: "slide",
    title: "See where your money is heading",
    body: "Your next few months, played forward from your own spending, income and bills.",
    picture: <ForecastPicture />,
  },
  {
    kind: "slide",
    title: "Check a pay-later buy before you commit",
    body: "Safe, Caution or At Risk, with the reasons, from your own figures.",
    picture: <RiskPicture />,
  },
  {
    kind: "slide",
    title: "Ask PaySense",
    body: "It explains and suggests. Nothing changes until you press Confirm.",
    picture: <AssistantPicture />,
  },
  {
    kind: "slide",
    title: "Your data stays yours",
    body: "Download or delete everything, any time, under Your data.",
    picture: <TickPicture rows={["Download everything", "Delete everything", "Assistant asks first"]} />,
  },
];

const NOTICE: Step = {
  kind: "notice",
  title: "Before you start",
  body: "The short version is below. Open the full notice for the details.",
  picture: <NoticePicture />,
};

const FINISH: Step = {
  kind: "finish",
  title: "You're all set",
  body: "Import a statement for a forecast on your own records, or look around first.",
  picture: <FinishPicture />,
};

const LINK_PRIMARY =
  "inline-flex h-10 items-center rounded-xl bg-accent px-4 text-[13px] font-semibold text-white transition-colors hover:bg-accent/90";
const LINK_SECONDARY =
  "inline-flex h-10 items-center rounded-xl border border-line bg-surface px-4 text-[13px] font-semibold text-ink transition-colors hover:bg-surface-2";

type Props = {
  /** Include the four "what PaySense is" slides. */
  slides: boolean;
  /** The privacy notice still to accept, if any: it becomes a step that cannot be skipped. */
  notice?: Consent;
  onDone: () => void;
  /** Given for a replay over the app: a Close button and Escape, as a modal dialog. */
  onClose?: () => void;
};

/**
 * Onboarding, full screen: what PaySense is (slides), the privacy notice when it is due, and where
 * to begin. On first sign-in it stands in for the app; from the profile menu it replays the slides.
 */
export function Onboarding({ slides, notice, onDone, onClose }: Props) {
  const [steps] = useState(() => [...(slides ? SLIDES : []), ...(notice ? [NOTICE] : []), FINISH]);
  const [index, setIndex] = useState(0);
  const [dir, setDir] = useState<"next" | "back">("next");
  const heading = useRef<HTMLHeadingElement>(null);
  const accept = useAcceptConsent();
  const noticeAt = steps.indexOf(NOTICE);
  // Nobody moves past the notice without accepting it.
  const last = noticeAt >= 0 && !accept.isSuccess ? noticeAt : steps.length - 1;
  const step = steps[index];

  useEffect(() => heading.current?.focus(), [index]);

  function go(to: number) {
    const next = Math.min(Math.max(to, 0), last);
    if (next === index) return;
    setDir(next > index ? "next" : "back");
    setIndex(next);
  }

  function finish() {
    markIntroSeen();
    onDone();
  }

  function onKeyDown(event: KeyboardEvent) {
    if (event.key === "ArrowRight") go(index + 1);
    if (event.key === "ArrowLeft") go(index - 1);
    if (event.key === "Escape" && onClose) onClose();
  }

  const Heading = onClose ? "h2" : "h1";
  const frame = onClose
    ? ({ role: "dialog", "aria-modal": true, "aria-label": "Welcome to PaySense" } as const)
    : ({ role: "region", "aria-label": "Getting to know PaySense" } as const);

  return (
    <div {...frame} onKeyDown={onKeyDown} className="fixed inset-0 z-50 overflow-y-auto bg-page">
      <div className="mx-auto grid min-h-full max-w-6xl gap-4 p-4 md:grid-cols-[minmax(0,1.1fr)_minmax(0,1fr)] md:p-6">
        <div
          aria-hidden
          className="relative isolate flex min-h-64 flex-col overflow-hidden rounded-[28px] bg-accent p-6 md:p-10"
        >
          <div className="ob-ring -z-10 h-[300px] w-[300px]" />
          <div className="ob-ring -z-10 h-[480px] w-[480px] opacity-70" />
          <div className="ob-ring -z-10 h-[660px] w-[660px] opacity-40" />
          <div className="flex items-center gap-2.5">
            <BrandMark className="h-9 w-9" />
            <span className="font-display text-[20px] font-bold text-on-accent">
              Pay<span className="text-rose">Sense</span>
            </span>
          </div>
          <div key={index} className={`ob-in-${dir} m-auto w-full max-w-md py-6`}>
            <div className="ob-float aspect-[4/3] rounded-3xl bg-surface p-5 shadow-2xl">
              {step.picture}
            </div>
          </div>
        </div>

        <div className="flex flex-col rounded-[28px] bg-surface p-6 md:p-10">
          <div className="flex items-center justify-between gap-3">
            <div aria-hidden className="flex flex-1 gap-1.5">
              {steps.map((s, i) => (
                <span
                  key={s.title}
                  className={`h-1.5 flex-1 rounded-full transition-colors duration-500 ${i <= index ? "bg-accent" : "bg-line"}`}
                />
              ))}
            </div>
            {onClose ? (
              <Button variant="secondary" size="sm" onClick={onClose}>
                Close
              </Button>
            ) : (
              step.kind === "slide" && (
                <button
                  type="button"
                  onClick={() => (noticeAt >= 0 ? go(noticeAt) : finish())}
                  className="rounded-xl px-2 py-1 text-[13px] font-semibold text-ink-secondary hover:text-ink"
                >
                  Skip
                </button>
              )
            )}
          </div>

          <div key={index} className={`ob-in-${dir} flex-1 py-8`}>
            <p className="text-[12px] font-semibold uppercase tracking-wider text-accent">
              Step {index + 1} of {steps.length}
            </p>
            <Heading
              ref={heading}
              tabIndex={-1}
              className="mt-2 font-display text-[28px] font-bold leading-tight text-ink outline-none md:text-[34px]"
            >
              {step.title}
            </Heading>
            <p className="mt-3 text-[15px] leading-relaxed text-ink-secondary">{step.body}</p>
            {step.kind === "notice" && notice && (
              <>
                <ul className="mt-6 space-y-2">
                  {notice.sections.map((section, i) => (
                    <li
                      key={section.title}
                      className="intro-rise flex items-center gap-2.5 text-[14px] font-medium text-ink"
                      style={after(0.08 * i)}
                    >
                      <span
                        aria-hidden
                        className="flex h-5 w-5 shrink-0 items-center justify-center rounded-full bg-accent-bg text-[11px] text-accent"
                      >
                        ✓
                      </span>
                      {section.title}
                    </li>
                  ))}
                </ul>
                <details className="mt-5 rounded-2xl border border-line bg-surface-2 p-4">
                  <summary className="cursor-pointer text-[13px] font-semibold text-accent">
                    Read the full notice
                  </summary>
                  <div className="mt-3 max-h-64 overflow-y-auto pr-1">
                    <ConsentText consent={notice} />
                  </div>
                </details>
              </>
            )}
            {step.kind === "notice" && accept.isError && (
              <div className="mt-4">
                <ErrorState message={accept.error.message} />
              </div>
            )}
          </div>

          <div className="flex flex-wrap items-center justify-end gap-2">
            {index > 0 && step.kind !== "finish" && (
              <Button variant="secondary" onClick={() => go(index - 1)} className="mr-auto">
                Back
              </Button>
            )}
            {step.kind === "slide" && (
              <Button variant="accent" onClick={() => go(index + 1)}>
                Next
              </Button>
            )}
            {step.kind === "notice" && notice && (
              <Button
                variant="accent"
                disabled={accept.isPending}
                onClick={() =>
                  accept.mutate(notice.version, {
                    onSuccess: () => {
                      setDir("next");
                      setIndex(noticeAt + 1);
                    },
                  })
                }
              >
                {accept.isPending ? "Saving…" : "I understand, continue"}
              </Button>
            )}
            {step.kind === "finish" && (
              <>
                <Link href="/import" onClick={finish} className={LINK_SECONDARY}>
                  Import a statement
                </Link>
                <Link href="/" onClick={finish} className={LINK_PRIMARY}>
                  Go to the dashboard
                </Link>
              </>
            )}
          </div>
        </div>
      </div>
    </div>
  );
}

/** Freezes what is due when the gate first decides, so accepting the notice cannot reshuffle steps. */
function Gate({ notice, children }: { notice?: Consent; children: ReactNode }) {
  const [start] = useState(() => ({ notice, slides: !introSeen() }));
  const [done, setDone] = useState(false);
  if (done || (!start.notice && !start.slides)) return <>{children}</>;
  return <Onboarding slides={start.slides} notice={start.notice} onDone={() => setDone(true)} />;
}

/**
 * First sign-in (WP19): onboarding stands in for the app until the notice is accepted (once per
 * version) and the slides are seen (once per browser). The server enforces the notice where it
 * matters (the assistant will not call its model provider until it is accepted), so if the notice
 * cannot be loaded the app still opens.
 */
export function OnboardingGate({ children }: { children: ReactNode }) {
  const consent = useConsent();
  if (consent.isPending) {
    return (
      <div className="mx-auto max-w-2xl p-6">
        <Skeleton lines={4} label="Loading" />
      </div>
    );
  }
  return (
    <Gate notice={consent.data?.accepted === false ? consent.data : undefined}>{children}</Gate>
  );
}
