import type { ButtonHTMLAttributes, Ref } from "react";

type Variant = "primary" | "secondary" | "danger" | "accent";

type Props = ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: Variant;
  size?: "sm" | "md";
  /** React 19 passes a ref as an ordinary prop (used to return focus to a trigger). */
  ref?: Ref<HTMLButtonElement>;
};

const VARIANT_CLASSES: Record<Variant, string> = {
  primary: "bg-ink text-white border-transparent hover:bg-ink/85",
  secondary: "bg-surface text-ink border-line hover:bg-surface-2",
  danger: "bg-danger text-white border-transparent hover:bg-danger/85",
  accent: "bg-accent text-white border-transparent hover:bg-accent/90",
};

export function Button({ variant = "primary", size = "md", className = "", ...rest }: Props) {
  const sizeClasses = size === "sm" ? "h-8 px-3 text-xs" : "h-10 px-4 text-[13px]";
  return (
    <button
      type="button"
      className={`inline-flex items-center justify-center gap-1.5 rounded-lg border font-semibold transition-colors disabled:cursor-not-allowed disabled:opacity-50 ${VARIANT_CLASSES[variant]} ${sizeClasses} ${className}`}
      {...rest}
    />
  );
}
