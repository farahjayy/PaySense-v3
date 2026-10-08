import type { InputHTMLAttributes, ReactNode } from "react";
import { useId } from "react";

type FieldShellProps = {
  label: string;
  htmlFor: string;
  hint?: string;
  hintId?: string;
  error?: string | null;
  errorId?: string;
  children: ReactNode;
};

function FieldShell({ label, htmlFor, hint, hintId, error, errorId, children }: FieldShellProps) {
  return (
    <div className="flex flex-col gap-1.5">
      <label htmlFor={htmlFor} className="text-xs font-medium text-ink-secondary">
        {label}
      </label>
      {children}
      {hint && (
        <span id={hintId} className="text-[12px] text-ink-secondary">
          {hint}
        </span>
      )}
      {error && (
        <span id={errorId} role="alert" className="text-[12px] font-medium text-danger">
          {error}
        </span>
      )}
    </div>
  );
}

const INPUT_CLASSES =
  "h-10 rounded-lg border border-line bg-surface px-3 text-[14px] text-ink placeholder:text-ink-muted hover:border-ink-muted read-only:bg-surface-2";

type TextFieldProps = InputHTMLAttributes<HTMLInputElement> & {
  label: string;
  hint?: string;
  error?: string | null;
};

export function TextField({ label, hint, error, id, className = "", ...rest }: TextFieldProps) {
  const generatedId = useId();
  const inputId = id ?? generatedId;
  const hintId = hint ? `${inputId}-hint` : undefined;
  const errorId = error ? `${inputId}-error` : undefined;
  const describedBy = [hintId, errorId].filter(Boolean).join(" ") || undefined;
  return (
    <FieldShell
      label={label}
      htmlFor={inputId}
      hint={hint}
      hintId={hintId}
      error={error}
      errorId={errorId}
    >
      <input
        id={inputId}
        aria-invalid={error ? true : undefined}
        aria-describedby={describedBy}
        className={`${INPUT_CLASSES} ${className}`}
        {...rest}
      />
    </FieldShell>
  );
}
