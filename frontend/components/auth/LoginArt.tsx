import type { ReactNode } from "react";

/** The small drawings on the login page. All decorative: the words next to them carry the meaning. */

export type BandKey = "safe" | "caution" | "risk";

export function BrandMark() {
  return (
    <svg className="lg-brand-mark" viewBox="0 0 40 40" aria-hidden="true">
      <rect className="lg-mark-page" width="40" height="40" rx="12" />
      <path className="lg-mark-teal" d="M19 9.5a10.5 10.5 0 1 0 0 21z" />
      <path className="lg-mark-rosy" d="M22 9.5a10.5 10.5 0 0 1 10.5 10.5H22z" />
      <path className="lg-mark-teal" fillOpacity=".45" d="M22 23h10.3A10.5 10.5 0 0 1 22 30.5z" />
    </svg>
  );
}

const FACES: Record<BandKey, ReactNode> = {
  safe: (
    <>
      <circle cx="35" cy="43" r="5" fill="currentColor" />
      <circle cx="65" cy="43" r="5" fill="currentColor" />
      <path
        d="M34 60q16 15 32 0"
        fill="none"
        stroke="currentColor"
        strokeWidth="5"
        strokeLinecap="round"
      />
      <circle className="lg-cheek" cx="23" cy="58" r="6" />
      <circle className="lg-cheek" cx="77" cy="58" r="6" />
    </>
  ),
  caution: (
    <>
      <circle cx="35" cy="45" r="5" fill="currentColor" />
      <circle cx="65" cy="45" r="5" fill="currentColor" />
      <path d="M27 33l15-3" stroke="currentColor" strokeWidth="4.5" strokeLinecap="round" />
      <path
        d="M36 66q7-5 14 0t14 0"
        fill="none"
        stroke="currentColor"
        strokeWidth="5"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </>
  ),
  risk: (
    <>
      <circle cx="35" cy="47" r="5" fill="currentColor" />
      <circle cx="65" cy="47" r="5" fill="currentColor" />
      <path
        d="M27 38l15-7M73 38l-15-7"
        stroke="currentColor"
        strokeWidth="4.5"
        strokeLinecap="round"
      />
      <path
        d="M38 69q12-9 24 0"
        fill="none"
        stroke="currentColor"
        strokeWidth="5"
        strokeLinecap="round"
      />
      <path d="M80 28q5 7 0 11-5-4 0-11z" fill="currentColor" fillOpacity=".55" />
    </>
  ),
};

export function BandFace({ band }: { band: BandKey }) {
  return (
    <svg className={`lg-face lg-face-${band}`} viewBox="0 0 100 100" aria-hidden="true">
      <rect className="lg-face-tile" width="100" height="100" rx="30" />
      {FACES[band]}
    </svg>
  );
}

export function HelloFace() {
  return (
    <svg className="lg-hello" viewBox="0 0 100 100" aria-hidden="true">
      <rect className="lg-hello-tile" width="100" height="100" rx="30" />
      <circle cx="35" cy="42" r="5.5" fill="var(--lg-ink)" />
      <circle cx="65" cy="42" r="5.5" fill="var(--lg-ink)" />
      <path
        d="M32 59q18 18 36 0"
        fill="none"
        stroke="var(--lg-ink)"
        strokeWidth="5.5"
        strokeLinecap="round"
      />
    </svg>
  );
}

const ICON_PROPS = {
  fill: "none",
  stroke: "currentColor",
  strokeLinecap: "round",
  strokeLinejoin: "round",
  "aria-hidden": true,
} as const;

export function EyeIcon() {
  return (
    <svg width="22" height="22" viewBox="0 0 24 24" strokeWidth="1.9" {...ICON_PROPS}>
      <path d="M2 12s3.6-7 10-7 10 7 10 7-3.6 7-10 7S2 12 2 12z" />
      <circle cx="12" cy="12" r="3" />
    </svg>
  );
}

export function EyeOffIcon() {
  return (
    <svg width="22" height="22" viewBox="0 0 24 24" strokeWidth="1.9" {...ICON_PROPS}>
      <path d="M3 3l18 18" />
      <path d="M10.6 5.1A10.4 10.4 0 0 1 12 5c6.4 0 10 7 10 7a17 17 0 0 1-3.2 4.2M6.6 6.6A17 17 0 0 0 2 12s3.6 7 10 7c1.7 0 3.2-.4 4.5-1" />
      <path d="M9.9 9.9a3 3 0 0 0 4.2 4.2" />
    </svg>
  );
}

export function ArrowIcon() {
  return (
    <svg width="20" height="20" viewBox="0 0 24 24" strokeWidth="2.2" {...ICON_PROPS}>
      <path d="M5 12h14M13 6l6 6-6 6" />
    </svg>
  );
}
