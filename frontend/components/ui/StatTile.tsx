import type { ReactNode } from "react";

type Props = { label: string; value: ReactNode; note?: ReactNode };

/** One number with its name and, if it needs one, the sentence that qualifies it. */
export function StatTile({ label, value, note }: Props) {
  return (
    <div className="rounded-card border border-line bg-surface px-4 py-3.5">
      <p className="text-[11px] font-medium uppercase tracking-wide text-ink-muted">{label}</p>
      <p className="mt-1 font-serif text-2xl font-semibold tabular-nums tracking-tight text-ink">
        {value}
      </p>
      {note && <p className="mt-1 text-[12px] leading-snug text-ink-secondary">{note}</p>}
    </div>
  );
}
