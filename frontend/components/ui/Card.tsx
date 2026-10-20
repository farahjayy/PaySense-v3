import type { HTMLAttributes, ReactNode } from "react";

export function Card({ className = "", ...rest }: HTMLAttributes<HTMLDivElement>) {
  return (
    <div
      className={`rounded-card border border-line bg-surface p-4 sm:p-5 ${className}`}
      {...rest}
    />
  );
}

export function CardTitle({ children }: { children: ReactNode }) {
  return <h2 className="font-display text-[15px] font-semibold text-ink">{children}</h2>;
}

export function CardCaption({ children }: { children: ReactNode }) {
  return <p className="mt-0.5 text-[12px] leading-relaxed text-ink-secondary">{children}</p>;
}
