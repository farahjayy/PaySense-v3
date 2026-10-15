"use client";

type Kind = "income" | "expense" | "savings";

const OPTIONS: readonly { value: Kind | undefined; label: string }[] = [
  { value: undefined, label: "All" },
  { value: "income", label: "Income" },
  { value: "expense", label: "Spending" },
  { value: "savings", label: "Savings" },
];

type Props = { value: Kind | undefined; onChange: (value: Kind | undefined) => void };

/** Four choices that are always on screen, so one tap changes the list. */
export function TypeButtons({ value, onChange }: Props) {
  return (
    <div
      role="group"
      aria-label="Type"
      className="inline-flex overflow-hidden rounded-lg border border-field bg-surface"
    >
      {OPTIONS.map((option) => {
        const pressed = option.value === value;
        return (
          <button
            key={option.label}
            type="button"
            aria-pressed={pressed}
            onClick={() => onChange(option.value)}
            className={`h-9 border-l border-line px-3 text-[13px] font-medium first:border-l-0 ${
              pressed ? "bg-accent-bg font-semibold text-accent" : "text-ink hover:bg-surface-2"
            }`}
          >
            {option.label}
          </button>
        );
      })}
    </div>
  );
}
