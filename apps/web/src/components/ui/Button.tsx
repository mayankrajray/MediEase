import type { ButtonHTMLAttributes } from "react";

import { cx } from "./cx";

export type ButtonVariant = "primary" | "secondary" | "ghost" | "danger";
export type ButtonSize = "sm" | "md";

const VARIANTS: Record<ButtonVariant, string> = {
  primary: "bg-brand-700 text-white hover:bg-brand-800 disabled:bg-slate-400",
  secondary: "border border-slate-400 bg-white text-slate-900 hover:bg-slate-100 disabled:text-slate-500",
  ghost: "text-slate-800 hover:bg-slate-100 disabled:text-slate-500",
  danger: "bg-red-700 text-white hover:bg-red-800 disabled:bg-slate-400",
};

const SIZES: Record<ButtonSize, string> = {
  // Both at least 24 px tall (WCAG 2.2 target size); md is the 40 px touch size.
  sm: "min-h-8 px-3 py-1 text-sm",
  md: "min-h-10 px-4 py-2",
};

/** The classes of a button, for a `Link` that should look like one. */
export function buttonClasses(variant: ButtonVariant = "secondary", size: ButtonSize = "md"): string {
  return cx(
    "inline-flex items-center justify-center gap-2 rounded-lg font-medium transition-colors motion-reduce:transition-none disabled:cursor-not-allowed",
    VARIANTS[variant],
    SIZES[size],
  );
}

/** A button. `type` defaults to "button", so it never submits a form by accident. */
export function Button({
  variant = "secondary",
  size = "md",
  className,
  type = "button",
  ...rest
}: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: ButtonVariant; size?: ButtonSize }) {
  return <button type={type} className={cx(buttonClasses(variant, size), className)} {...rest} />;
}
