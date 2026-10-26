"use client";

import type { HTMLInputAutoCompleteAttribute, HTMLInputTypeAttribute, ReactNode } from "react";

import { cx } from "./cx";

/**
 * Form fields (M6-P2, decision 6A): one label, hint and error wiring for every control. The
 * error is text linked with `aria-describedby` and marks the control `aria-invalid`, so state is
 * never carried by colour alone (apps/web/CLAUDE.md). Controls are at least 40 px tall.
 * `INPUT`, `LABEL` and `HINT` style a hand-built control the same way.
 */
export const INPUT =
  "min-h-10 w-full rounded-lg border border-slate-400 bg-white px-3 py-2 text-slate-900 placeholder:text-slate-500 hover:border-slate-500 aria-[invalid=true]:border-red-700 disabled:bg-slate-100 disabled:text-slate-600";
export const LABEL = "block font-medium text-slate-900";
export const HINT = "text-sm text-slate-700";
export const ERROR = "text-sm font-medium text-red-900";

interface Described {
  readonly id: string;
  readonly label: string;
  readonly error?: string | undefined;
  readonly hint?: string;
  readonly required?: boolean;
}

function describedBy(id: string, hint: string | undefined, error: string | undefined): string | undefined {
  const parts = [hint !== undefined ? `${id}-hint` : null, error !== undefined ? `${id}-error` : null].filter(
    (part) => part !== null,
  );
  return parts.length === 0 ? undefined : parts.join(" ");
}

function FieldShell({ id, label, error, hint, required = false, children }: Described & { children: ReactNode }) {
  return (
    <div className="space-y-1">
      <label htmlFor={id} className={LABEL}>
        {label}
        {required && <span className="font-normal text-slate-700"> (required)</span>}
      </label>
      {children}
      {hint !== undefined && (
        <p id={`${id}-hint`} className={HINT}>
          {hint}
        </p>
      )}
      {error !== undefined && (
        <p id={`${id}-error`} className={ERROR}>
          {error}
        </p>
      )}
    </div>
  );
}

/** A labelled text input with its hint and its own error. */
export function TextField({
  id,
  label,
  value,
  onChange,
  error,
  hint,
  required = false,
  type = "text",
  autoComplete,
  maxLength,
  inputMode,
}: Described & {
  value: string;
  onChange: (value: string) => void;
  type?: HTMLInputTypeAttribute;
  autoComplete?: HTMLInputAutoCompleteAttribute;
  maxLength?: number;
  inputMode?: "text" | "numeric" | "tel" | "email";
}) {
  return (
    <FieldShell id={id} label={label} error={error} {...(hint === undefined ? {} : { hint })} required={required}>
      <input
        id={id}
        name={id}
        type={type}
        value={value}
        required={required}
        autoComplete={autoComplete ?? "off"}
        maxLength={maxLength}
        inputMode={inputMode}
        aria-invalid={error !== undefined ? true : undefined}
        aria-describedby={describedBy(id, hint, error)}
        onChange={(event) => onChange(event.target.value)}
        className={INPUT}
      />
    </FieldShell>
  );
}

/** A labelled `<select>` of the given options. */
export function SelectField({
  id,
  label,
  value,
  onChange,
  options,
  error,
  hint,
  required = false,
}: Described & {
  value: string;
  onChange: (value: string) => void;
  options: readonly { readonly value: string; readonly label: string }[];
}) {
  return (
    <FieldShell id={id} label={label} error={error} {...(hint === undefined ? {} : { hint })} required={required}>
      <select
        id={id}
        name={id}
        value={value}
        required={required}
        aria-invalid={error !== undefined ? true : undefined}
        aria-describedby={describedBy(id, hint, error)}
        onChange={(event) => onChange(event.target.value)}
        className={INPUT}
      >
        {options.map((o) => (
          <option key={o.value} value={o.value}>
            {o.label}
          </option>
        ))}
      </select>
    </FieldShell>
  );
}

/** A labelled multi-line text box. */
export function TextAreaField({
  id,
  label,
  value,
  onChange,
  error,
  hint,
  required = false,
  rows = 3,
  maxLength,
}: Described & { value: string; onChange: (value: string) => void; rows?: number; maxLength?: number }) {
  return (
    <FieldShell id={id} label={label} error={error} {...(hint === undefined ? {} : { hint })} required={required}>
      <textarea
        id={id}
        name={id}
        value={value}
        rows={rows}
        required={required}
        maxLength={maxLength}
        aria-invalid={error !== undefined ? true : undefined}
        aria-describedby={describedBy(id, hint, error)}
        onChange={(event) => onChange(event.target.value)}
        className={INPUT}
      />
    </FieldShell>
  );
}

/** A checkbox with its label beside it and an optional hint under it. */
export function CheckboxField({
  id,
  label,
  checked,
  onChange,
  hint,
  error,
  disabled,
}: Omit<Described, "required"> & { checked: boolean; onChange: (checked: boolean) => void; disabled?: boolean }) {
  return (
    <div className="space-y-1">
      <div className="flex min-h-10 items-center gap-3">
        <input
          id={id}
          name={id}
          type="checkbox"
          checked={checked}
          disabled={disabled}
          aria-invalid={error !== undefined ? true : undefined}
          aria-describedby={describedBy(id, hint, error)}
          onChange={(event) => onChange(event.target.checked)}
          className={cx("size-5 rounded border-slate-400 accent-brand-700")}
        />
        <label htmlFor={id} className="font-medium text-slate-900">
          {label}
        </label>
      </div>
      {hint !== undefined && (
        <p id={`${id}-hint`} className={cx(HINT, "pl-8")}>
          {hint}
        </p>
      )}
      {error !== undefined && (
        <p id={`${id}-error`} className={cx(ERROR, "pl-8")}>
          {error}
        </p>
      )}
    </div>
  );
}
