import type { InputHTMLAttributes, ReactNode } from "react";
import { useId } from "react";

type FieldShellProps = {
  label: string;
  htmlFor: string;
  hint?: string;
  error?: string | null;
  children: ReactNode;
};

function FieldShell({ label, htmlFor, hint, error, children }: FieldShellProps) {
  return (
    <div className="flex flex-col gap-1.5">
      <label htmlFor={htmlFor} className="text-xs font-medium text-ink-secondary">
        {label}
      </label>
      {children}
      {hint && <span className="text-[11px] text-ink-muted">{hint}</span>}
      {error && (
        <span role="alert" className="text-[12px] font-medium text-danger">
          {error}
        </span>
      )}
    </div>
  );
}

const INPUT_CLASSES =
  "h-10 rounded-lg border border-line bg-surface px-3 text-[14px] text-ink placeholder:text-ink-muted hover:border-ink-muted";

type TextFieldProps = InputHTMLAttributes<HTMLInputElement> & {
  label: string;
  hint?: string;
  error?: string | null;
};

export function TextField({ label, hint, error, id, className = "", ...rest }: TextFieldProps) {
  const generatedId = useId();
  const inputId = id ?? generatedId;
  return (
    <FieldShell label={label} htmlFor={inputId} hint={hint} error={error}>
      <input
        id={inputId}
        aria-invalid={error ? true : undefined}
        className={`${INPUT_CLASSES} ${className}`}
        {...rest}
      />
    </FieldShell>
  );
}
