import { BAND_COPY, type Band } from "@/lib/format";

const SIZE = 148;
const STROKE = 12;
const RADIUS = (SIZE - STROKE) / 2;
const CIRCUMFERENCE = 2 * Math.PI * RADIUS;

const STROKE_COLOUR = {
  success: "var(--color-success)",
  warning: "var(--color-warning)",
  danger: "var(--color-danger)",
} as const;

type Props = { score: number; band: Band; caption?: string };

/** The 0-100 score as a ring and a large number; the same facts are in the accessible name. */
export function ScoreRing({ score, band, caption = "out of 100" }: Props) {
  const clamped = Math.max(0, Math.min(100, score));
  const tone = BAND_COPY[band].tone;
  return (
    <div
      role="img"
      aria-label={`Score ${clamped} out of 100, ${band}`}
      className="relative inline-flex"
      style={{ width: SIZE, height: SIZE }}
    >
      <svg width={SIZE} height={SIZE} viewBox={`0 0 ${SIZE} ${SIZE}`} aria-hidden>
        <circle
          cx={SIZE / 2}
          cy={SIZE / 2}
          r={RADIUS}
          fill="none"
          stroke="var(--color-line)"
          strokeWidth={STROKE}
        />
        <circle
          cx={SIZE / 2}
          cy={SIZE / 2}
          r={RADIUS}
          fill="none"
          stroke={STROKE_COLOUR[tone]}
          strokeWidth={STROKE}
          strokeLinecap="round"
          strokeDasharray={`${(clamped / 100) * CIRCUMFERENCE} ${CIRCUMFERENCE}`}
          transform={`rotate(-90 ${SIZE / 2} ${SIZE / 2})`}
        />
      </svg>
      <div className="absolute inset-0 flex flex-col items-center justify-center" aria-hidden>
        <span className="font-display text-[40px] font-semibold leading-none tracking-tight text-ink">
          {clamped}
        </span>
        <span className="mt-1 text-[11px] text-ink-muted">{caption}</span>
      </div>
    </div>
  );
}
