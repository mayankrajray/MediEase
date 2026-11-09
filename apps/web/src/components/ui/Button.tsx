import type { ButtonHTMLAttributes, ReactNode } from "react";

import { cx } from "./cx";
import { Spinner } from "./Spinner";

export type ButtonVariant = "primary" | "secondary" | "ghost" | "danger";
export type ButtonSize = "sm" | "md" | "lg";

const VARIANTS: Record<ButtonVariant, string> = {
  primary:
    "bg-brand-700 text-white shadow-sm hover:bg-brand-800 disabled:bg-slate-300 disabled:text-slate-700 disabled:shadow-none",
  secondary:
    "border border-slate-300 bg-white text-slate-900 shadow-sm hover:border-slate-400 hover:bg-slate-50 disabled:bg-slate-100 disabled:text-slate-500 disabled:shadow-none",
  ghost: "text-slate-800 hover:bg-slate-100 disabled:text-slate-500",
  danger:
    "bg-danger text-white shadow-sm hover:bg-red-800 disabled:bg-slate-300 disabled:text-slate-700 disabled:shadow-none",
};

const SIZES: Record<ButtonSize, string> = {
  // All at least 24 px tall (WCAG 2.2 target size); md is the 40 px clinic size, lg the 48 px
  // patient and landing size (DESIGN.md §5).
  sm: "min-h-8 px-3 py-1 text-sm",
  md: "min-h-10 px-4 py-2 text-base",
  lg: "min-h-12 px-5 py-2.5 text-base",
};

/** The classes of a button, for a `Link` that should look like one. */
export function buttonClasses(variant: ButtonVariant = "secondary", size: ButtonSize = "md"): string {
  return cx(
    "inline-flex select-none items-center justify-center gap-2 rounded-lg font-semibold transition duration-200 ease-brand",
    "active:translate-y-px disabled:cursor-not-allowed disabled:active:translate-y-0 motion-reduce:transition-none motion-reduce:active:translate-y-0",
    VARIANTS[variant],
    SIZES[size],
  );
}

/**
 * A button. `type` defaults to "button", so it never submits a form by accident.
 *
 * M7c-P7: `loading` keeps the button's label (so its width and its accessible name stay), shows
 * a spinner before it, marks it `aria-busy` and disables it, so a second click cannot repeat the
 * action. `icon` puts a decorative icon before the label.
 */
export function Button({
  variant = "secondary",
  size = "md",
  className,
  type = "button",
  loading = false,
  icon,
  disabled,
  children,
  ...rest
}: ButtonHTMLAttributes<HTMLButtonElement> & {
  variant?: ButtonVariant;
  size?: ButtonSize;
  loading?: boolean;
  icon?: ReactNode;
}) {
  return (
    <button
      type={type}
      className={cx(buttonClasses(variant, size), className)}
      disabled={disabled === true || loading}
      aria-busy={loading || undefined}
      {...rest}
    >
      {loading ? <Spinner /> : icon !== undefined && <span aria-hidden="true" className="inline-flex shrink-0">{icon}</span>}
      {children}
    </button>
  );
}
