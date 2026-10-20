import type { Metadata } from "next";
import Link from "next/link";
import type { CSSProperties } from "react";

import { ArrowIcon, BandFace, BrandMark, type BandKey } from "@/components/auth/LoginArt";
import { LocalTerms } from "@/components/ui/LocalTerms";
import type { Band } from "@/lib/format";

export const metadata: Metadata = { title: "Welcome" };

// Each element's entrance waits its turn; reduced motion shows the finished page.
const after = (seconds: number): CSSProperties => ({ animationDelay: `${seconds}s` });

const BANDS: readonly { band: Band; key: BandKey }[] = [
  { band: "Safe", key: "safe" },
  { band: "Caution", key: "caution" },
  { band: "At Risk", key: "risk" },
];

const STEPS = [
  {
    title: "Bring in your money",
    text: "Import a bank or e-wallet statement, or add transactions yourself. You review everything before it is saved.",
  },
  {
    title: "See where it is heading",
    text: "PaySense plays your next few months forward from your own spending, income and bills, as a likely range rather than one guess.",
  },
  {
    title: "Check before you split",
    text: "Describe a buy-now-pay-later purchase and get Safe, Caution or At Risk, with the reasons behind it.",
  },
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
            <span key={key} className={`lg-chip lg-chip-${key} wl-pop`} style={after(1.9 + 0.2 * i)}>
              {band}
            </span>
          ))}
        </div>
      </div>
      <div className="wl-faces">
        {BANDS.map(({ key }, i) => (
          <span key={key} className="lg-band wl-pop" style={after(2.6 + 0.15 * i)}>
            <BandFace band={key} />
          </span>
        ))}
      </div>
    </div>
  );
}

/** What PaySense is, before anyone signs in: the pitch, how it works, and the way in. */
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
          Log in
        </Link>
      </header>

      <main>
        <section className="wl-hero">
          <div className="wl-hero-copy">
            <p className="wl-eyebrow wl-rise">For university students in Malaysia</p>
            <h1 className="wl-rise" style={after(0.1)}>
              Think before you <em>split.</em>
            </h1>
            <p className="wl-lede wl-rise" style={after(0.2)}>
              PaySense looks at your own spending, income and bills, plays the next few months
              forward, and tells you whether a buy-now-pay-later plan fits before you commit.
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

        <section aria-labelledby="ready-title" className="wl-ready wl-reveal">
          <div className="lg-rings" aria-hidden="true">
            <span />
            <span />
            <span />
          </div>
          <h2 id="ready-title">Ready when you are</h2>
          <p>Sign in, take the short tour, and see your own forecast.</p>
          <Link href="/login" className="wl-btn wl-btn-light">
            Get started <ArrowIcon />
          </Link>
        </section>
      </main>

      <footer className="wl-footer">
        <LocalTerms className="lg-terms" />
      </footer>
    </div>
  );
}
