import { BAND_COPY, type Band } from "@/lib/format";

const TONE_CLASSES = {
  success: "border-success/30 bg-success-bg text-success",
  warning: "border-warning/30 bg-warning-bg text-warning",
  danger: "border-danger/30 bg-danger-bg text-danger",
} as const;

/** The risk level as words and a glyph as well as a colour. */
export function BandBadge({ band, large = false }: { band: Band; large?: boolean }) {
  const copy = BAND_COPY[band];
  const size = large ? "px-3.5 py-1.5 text-sm" : "px-2.5 py-1 text-xs";
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full border font-semibold ${size} ${TONE_CLASSES[copy.tone]}`}
    >
      <span aria-hidden>{copy.icon}</span>
      <span className="sr-only">Risk level: </span>
      {band}
    </span>
  );
}
