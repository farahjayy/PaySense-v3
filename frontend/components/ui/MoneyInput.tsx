"use client";

import { useId, useState } from "react";

import { formatRm, parseRm } from "@/lib/money";

type Props = {
  label: string;
  /** Integer sen, or null when empty or not a valid amount. */
  valueSen: number | null;
  onChange: (sen: number | null) => void;
  hint?: string;
  error?: string | null;
  required?: boolean;
  disabled?: boolean;
};

/**
 * A ringgit field. What the person types is parsed by the shared money code (never parseFloat),
 * so 19.99 is 1999 sen. Invalid text is explained, not guessed at.
 */
export function MoneyInput({
  label,
  valueSen,
  onChange,
  hint,
  error,
  required,
  disabled,
}: Props) {
  const id = useId();
  const [text, setText] = useState(valueSen === null ? "" : formatRm(valueSen).replace("RM ", ""));
  const [touched, setTouched] = useState(false);

  const parsed = text.trim() === "" ? null : parseRm(text);
  const invalid = touched && text.trim() !== "" && parsed === null;
  const message = error ?? (invalid ? "Enter an amount like 12.50 or RM 1,200." : null);
  const hintId = hint ? `${id}-hint` : undefined;
  const errorId = message ? `${id}-error` : undefined;

  return (
    <div className="flex flex-col gap-1.5">
      <label htmlFor={id} className="text-xs font-medium text-ink-secondary">
        {label}
        {required && <span aria-hidden> *</span>}
      </label>
      <div className="relative">
        <span
          aria-hidden
          className="pointer-events-none absolute inset-y-0 left-3 flex items-center text-[13px] text-ink-muted"
        >
          RM
        </span>
        <input
          id={id}
          inputMode="decimal"
          autoComplete="off"
          required={required}
          disabled={disabled}
          value={text}
          aria-invalid={invalid || Boolean(error)}
          aria-describedby={[hintId, errorId].filter(Boolean).join(" ") || undefined}
          onChange={(event) => {
            setText(event.target.value);
            const next = event.target.value.trim() === "" ? null : parseRm(event.target.value);
            onChange(next);
          }}
          onBlur={() => setTouched(true)}
          className="h-10 w-full rounded-lg border border-line bg-surface pl-10 pr-3 text-right text-[14px] tabular-nums text-ink hover:border-ink-muted disabled:bg-surface-2"
        />
      </div>
      {hint && (
        <span id={hintId} className="text-[12px] text-ink-secondary">
          {hint}
        </span>
      )}
      {message && (
        <span id={errorId} role="alert" className="text-[12px] font-medium text-danger">
          {message}
        </span>
      )}
    </div>
  );
}
