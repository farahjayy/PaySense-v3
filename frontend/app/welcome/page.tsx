import type { Metadata } from "next";
import Link from "next/link";
import type { CSSProperties } from "react";

import {
  ArrowIcon,
  BandFace,
  BrandMark,
  type BandKey,
} from "@/components/auth/LoginArt";
import { LocalTerms } from "@/components/ui/LocalTerms";
import type { Band } from "@/lib/format";

export const metadata: Metadata = { title: "Welcome" };

// Each element's entrance waits its turn; reduced motion shows the finished page.
const after = (seconds: number): CSSProperties => ({
  animationDelay: `${seconds}s`,
});

const BANDS: readonly { band: Band; key: BandKey }[] = [
  { band: "Safe", key: "safe" },
  { band: "Caution", key: "caution" },
  { band: "At Risk", key: "risk" },
];

const STEPS = [
  {
    title: "Your money, in one place",
    text: "Bring in a bank or e-wallet statement, or add spending yourself. You check every line before it is saved.",
  },
  {
    title: "See the months ahead",
    text: "PaySense plays your next few months forward from your own spending, income and bills, as a likely range rather than one guess.",
  },
  {
    title: "Know before you split",
    text: "Describe a buy-now-pay-later purchase and get a clear answer, with the reasons behind it.",
  },
] as const;

const ANSWERS: readonly { key: BandKey; band: Band; text: string }[] = [
  {
    key: "safe",
    band: "Safe",
    text: "The instalments fit the months ahead, with room to spare.",
  },
  {
    key: "caution",
    band: "Caution",
    text: "It fits, but leaves little room. You see the reasons.",
  },
  {
    key: "risk",
    band: "At Risk",
    text: "It is likely to leave you short. You see what would change that.",
  },
];

const CONTROL = [
  "Nothing is saved until you have reviewed it.",
  "Ask PaySense in your own words; nothing in your data changes until you press Confirm.",
  "Download or delete everything PaySense holds about you, any time.",
  "Estimates from your own records, not financial advice and not a credit decision.",
] as const;

/** A forecast line draws in and its likely range opens out; a purchase gets its three answers. */
function HeroArt() {
  return (
    <div className="wl-art" aria-hidden="true">
      <div className="lg-pattern" />
      <div className="lg-rings">
        <span />
        <span />
        <span />
      </div>
      <div className="wl-chart-card wl-pop" style={after(0.3)}>
        <p className="wl-card-label">Your next few months</p>
        <svg viewBox="0 0 320 170" className="wl-chart">
          <line x1="10" y1="150" x2="310" y2="150" className="wl-axis" />
          <path d="M170 92 L310 46 L310 138 Z" className="wl-range" />
          <path
            d="M10 118 L45 106 L80 114 L115 90 L150 97 L170 92 L230 80 L310 92"
            pathLength={1}
            className="wl-line"
          />
          <line x1="170" y1="20" x2="170" y2="150" className="wl-today" />
          <circle cx="170" cy="92" r="7" className="wl-dot" />
        </svg>
      </div>
      <div className="wl-check-card wl-pop" style={after(1.4)}>
        <p className="wl-card-title">New phone</p>
        <p className="wl-card-label">Pay later, in instalments</p>
        <div className="wl-chips">
          {BANDS.map(({ band, key }, i) => (
            <span
              key={key}
              className={`lg-chip lg-chip-${key} wl-pop`}
              style={after(1.9 + 0.2 * i)}
            >
              {band}
            </span>
          ))}
        </div>
      </div>
      <div className="wl-faces">
        {BANDS.map(({ key }, i) => (
          <span
            key={key}
            className="lg-band wl-pop"
            style={after(2.6 + 0.15 * i)}
          >
            <BandFace band={key} />
          </span>
        ))}
      </div>
    </div>
  );
}

/** What PaySense does for a student, before anyone signs in, and the way in. */
export default function WelcomePage() {
  return (
    <div className="wl">
      <header className="wl-nav">
        <Link href="/welcome" className="wl-brand">
          <BrandMark />
          <span className="lg-brand-name">
            Pay<span>Sense</span>
          </span>
        </Link>
        <Link href="/login" className="wl-btn wl-btn-ghost">
          Sign in
        </Link>
      </header>

      <main>
        <section className="wl-hero">
          <div className="wl-hero-copy">
            <p className="wl-eyebrow wl-rise">
              For university students in Malaysia
            </p>
            <h1 className="wl-rise" style={after(0.1)}>
              Think before you <em>split.</em>
            </h1>
            <p className="wl-lede wl-rise" style={after(0.2)}>
              Know whether a buy-now-pay-later plan fits your next few months
              before you commit, worked out from your own spending, income and
              bills.
            </p>
            <div className="wl-ctas wl-rise" style={after(0.3)}>
              <Link href="/login" className="wl-btn wl-btn-primary">
                Get started <ArrowIcon />
              </Link>
              <a href="#how" className="wl-btn wl-btn-ghost">
                See how it works
              </a>
            </div>
          </div>
          <HeroArt />
        </section>

        <section aria-labelledby="why-title" className="wl-section wl-reveal">
          <h2 id="why-title">Small instalments add up</h2>
          <p className="wl-copy">
            Splitting a phone or a laptop into instalments makes it feel
            affordable today. But a student&apos;s money often arrives in lumps,
            once a semester or once a month, and a few plans running at once can
            outrun it. PaySense checks that for you before you say yes.
          </p>
        </section>

        <section id="how" aria-labelledby="how-title" className="wl-section">
          <h2 id="how-title" className="wl-reveal">
            How it works
          </h2>
          <ol className="wl-steps">
            {STEPS.map((step, i) => (
              <li key={step.title} className="wl-step wl-reveal">
                <span className="wl-step-n" aria-hidden="true">
                  {i + 1}
                </span>
                <h3>{step.title}</h3>
                <p>{step.text}</p>
              </li>
            ))}
          </ol>
        </section>

        <section aria-labelledby="answers-title" className="wl-section">
          <h2 id="answers-title" className="wl-reveal">
            One of three answers
          </h2>
          <ul className="wl-steps">
            {ANSWERS.map(({ key, band, text }) => (
              <li key={key} className="wl-step wl-reveal">
                <span className={`lg-chip lg-chip-${key}`}>{band}</span>
                <p className="wl-answer">{text}</p>
              </li>
            ))}
          </ul>
        </section>

        <section
          aria-labelledby="providers-title"
          className="wl-section wl-reveal"
        >
          <h2 id="providers-title">Knows the plans students use</h2>
          <p className="wl-copy">
            SPayLater, TikTok PayLater and Atome are built in, with their own
            billing rules. On any other provider, you enter the dates and
            amounts from your checkout.
          </p>
        </section>

        <section
          aria-labelledby="control-title"
          className="wl-section wl-reveal"
        >
          <h2 id="control-title">You stay in control</h2>
          <ul className="wl-control">
            {CONTROL.map((line) => (
              <li key={line}>{line}</li>
            ))}
          </ul>
        </section>

        <section aria-labelledby="ready-title" className="wl-ready wl-reveal">
          <div className="lg-rings" aria-hidden="true">
            <span />
            <span />
            <span />
          </div>
          <h2 id="ready-title">Ready when you are</h2>
          <p>
            Create a free account with your email, take the short tour, and see
            your own forecast.
          </p>
          <Link href="/login#signup" className="wl-btn wl-btn-light">
            Create your account <ArrowIcon />
          </Link>
        </section>
      </main>

      <footer className="wl-footer">
        <LocalTerms className="lg-terms" />
      </footer>
    </div>
  );
}
