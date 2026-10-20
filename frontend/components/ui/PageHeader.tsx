import type { ReactNode } from "react";

type Props = { title: string; intro?: ReactNode; actions?: ReactNode };

/** The top of every screen: one h1, a sentence on what the screen is for, and its main actions. */
export function PageHeader({ title, intro, actions }: Props) {
  return (
    <header className="mb-6 flex flex-wrap items-end justify-between gap-3">
      <div className="max-w-2xl">
        <h1
          tabIndex={-1}
          className="font-display outline-none text-[32px] font-bold leading-tight tracking-tight text-ink"
        >
          {title}
        </h1>
        {intro && <p className="mt-1.5 text-[14px] leading-relaxed text-ink-secondary">{intro}</p>}
      </div>
      {actions && <div className="flex flex-wrap items-center gap-2">{actions}</div>}
    </header>
  );
}
