"use client";

import { useState, type HTMLInputAutoCompleteAttribute, type HTMLInputTypeAttribute, type ReactNode, type Ref } from "react";

import { cx } from "./cx";

/**
 * Form fields (M6-P2, decision 6A): one label, hint and error wiring for every control. The
 * error is text linked with `aria-describedby` and marks the control `aria-invalid`, so state is
 * never carried by colour alone (apps/web/CLAUDE.md). Controls are at least 40 px tall.
 * `INPUT`, `LABEL` and `HINT` style a hand-built control the same way.
 */
export const INPUT =
  "min-h-10 w-full rounded-lg border border-slate-400 bg-white px-3 py-2 text-slate-900 shadow-xs transition-colors duration-200 ease-brand placeholder:text-slate-500 hover:border-slate-600 focus-visible:border-brand-700 focus-visible:outline-brand-700 aria-[invalid=true]:border-danger aria-[invalid=true]:bg-danger-soft/40 disabled:cursor-not-allowed disabled:bg-surface-muted disabled:text-slate-600 motion-reduce:transition-none";
export const LABEL = "block text-sm font-semibold text-slate-900";
export const HINT = "text-sm text-slate-700";
export const ERROR = "flex items-start gap-1.5 text-sm font-medium text-danger";

interface Described {
  readonly id: string;
  readonly label: string;
  readonly error?: string | undefined;
  readonly hint?: string;
  readonly required?: boolean;
}

function describedBy(id: string, hint: string | undefined, error: string | undefined, extra?: string): string | undefined {
  const parts = [
    hint !== undefined ? `${id}-hint` : null,
    error !== undefined ? `${id}-error` : null,
    extra ?? null,
  ].filter((part) => part !== null);
  return parts.length === 0 ? undefined : parts.join(" ");
}

function FieldShell({
  id,
  label,
  error,
  hint,
  required = false,
  requiredMark = true,
  errorLive = false,
  after,
  children,
}: Described & { requiredMark?: boolean; errorLive?: boolean; after?: ReactNode; children: ReactNode }) {
  return (
    <div className="space-y-1.5">
      <label htmlFor={id} className={LABEL}>
        {label}
        {required && requiredMark && <span className="font-normal text-slate-700"> (required)</span>}
      </label>
      {children}
      {hint !== undefined && (
        <p id={`${id}-hint`} className={HINT}>
          {hint}
        </p>
      )}
      {after}
      {error !== undefined && (
        <p id={`${id}-error`} role={errorLive ? "alert" : undefined} className={ERROR}>
          <span aria-hidden="true" className="mt-0.5 grid size-4 shrink-0 place-items-center rounded-full bg-danger text-[0.625rem] font-bold text-white">
            !
          </span>
          {error}
        </p>
      )}
    </div>
  );
}

/**
 * "120 of 200" under a field with a limit (DESIGN.md §8a): polite, so a screen reader hears it
 * without interruption; it turns amber in the last 10%.
 */
function Counter({ id, length, max }: { id: string; length: number; max: number }) {
  return (
    <p id={`${id}-count`} aria-live="polite" className={cx("text-right text-xs", length > max * 0.9 ? "text-warning" : "text-slate-600")} data-numeric>
      {length} of {max}
    </p>
  );
}

/**
 * A labelled text input with its hint and its own error. M7c-P7 (M2): `onBlur` lets a form check a
 * field when the person leaves it; `counter` shows "n of maxLength"; `requiredMark={false}` drops
 * the "(required)" word where every field of a short form is required (sign-in); `describedBy`
 * adds another description (a form-level error); `inputRef` lets a form move focus to it.
 */
export function TextField({
  id,
  label,
  value,
  onChange,
  onBlur,
  error,
  hint,
  required = false,
  requiredMark = true,
  type = "text",
  autoComplete,
  autoCapitalize,
  spellCheck,
  maxLength,
  counter = false,
  inputMode,
  describedBy: extra,
  inputRef,
}: Described & {
  value: string;
  onChange: (value: string) => void;
  onBlur?: () => void;
  requiredMark?: boolean;
  type?: HTMLInputTypeAttribute;
  autoComplete?: HTMLInputAutoCompleteAttribute;
  autoCapitalize?: "none" | "sentences" | "words";
  spellCheck?: boolean;
  maxLength?: number;
  counter?: boolean;
  inputMode?: "text" | "numeric" | "tel" | "email";
  describedBy?: string | undefined;
  inputRef?: Ref<HTMLInputElement>;
}) {
  const counted = counter && maxLength !== undefined;
  return (
    <FieldShell
      id={id}
      label={label}
      error={error}
      {...(hint === undefined ? {} : { hint })}
      required={required}
      requiredMark={requiredMark}
      after={counted ? <Counter id={id} length={value.length} max={maxLength} /> : undefined}
    >
      <input
        id={id}
        name={id}
        ref={inputRef}
        type={type}
        value={value}
        required={required}
        autoComplete={autoComplete ?? "off"}
        autoCapitalize={autoCapitalize}
        spellCheck={spellCheck}
        maxLength={maxLength}
        inputMode={inputMode}
        aria-invalid={error !== undefined ? true : undefined}
        aria-describedby={describedBy(id, hint, error, [extra, counted ? `${id}-count` : undefined].filter(Boolean).join(" ") || undefined)}
        onChange={(event) => onChange(event.target.value)}
        onBlur={onBlur}
        className={INPUT}
      />
    </FieldShell>
  );
}

/**
 * M7c-P7 (M2): a password with a visible *Show password* / *Hide password* button (named in words,
 * `aria-pressed`), and optionally the rules it must meet, each ticking off as it is met
 * (`requirements`): the list is described to screen readers with each rule's state in words.
 */
export function PasswordField({
  id,
  label,
  value,
  onChange,
  onBlur,
  error,
  hint,
  required = false,
  requiredMark = true,
  autoComplete,
  requirements,
  invalid = false,
  errorLive = false,
  describedBy: extra,
  inputRef,
  showLabel = "Show password",
  hideLabel = "Hide password",
  metLabel = "done",
  unmetLabel = "not yet",
}: Described & {
  value: string;
  onChange: (value: string) => void;
  onBlur?: () => void;
  requiredMark?: boolean;
  autoComplete: "current-password" | "new-password";
  requirements?: readonly { readonly label: string; readonly met: boolean }[];
  /** Marked invalid by a form-level error (a wrong password), whose words are elsewhere. */
  invalid?: boolean;
  /** The error is announced as soon as it appears (`role="alert"`), for a check made on submit. */
  errorLive?: boolean;
  describedBy?: string | undefined;
  inputRef?: Ref<HTMLInputElement>;
  showLabel?: string;
  hideLabel?: string;
  metLabel?: string;
  unmetLabel?: string;
}) {
  const [shown, setShown] = useState(false);
  const rules =
    requirements === undefined || requirements.length === 0 ? undefined : (
      <ul id={`${id}-rules`} className="space-y-1 text-sm">
        {requirements.map((r) => (
          <li key={r.label} className={cx("flex items-center gap-2", r.met ? "text-success" : "text-slate-700")}>
            <span
              aria-hidden="true"
              className={cx(
                "grid size-4 shrink-0 place-items-center rounded-full text-[0.625rem] font-bold transition-colors duration-200 ease-brand",
                r.met ? "bg-success text-white" : "border border-slate-400 text-transparent",
              )}
            >
              ✓
            </span>
            {r.label}
            <span className="sr-only">: {r.met ? metLabel : unmetLabel}</span>
          </li>
        ))}
      </ul>
    );
  return (
    <FieldShell id={id} label={label} error={error} {...(hint === undefined ? {} : { hint })} required={required} requiredMark={requiredMark} errorLive={errorLive} after={rules}>
      <div className="flex gap-2">
        <input
          id={id}
          name={id}
          ref={inputRef}
          type={shown ? "text" : "password"}
          value={value}
          required={required}
          autoComplete={autoComplete}
          autoCapitalize="none"
          spellCheck={false}
          aria-invalid={error !== undefined || invalid ? true : undefined}
          aria-describedby={describedBy(id, hint, error, [rules === undefined ? undefined : `${id}-rules`, extra].filter(Boolean).join(" ") || undefined)}
          onChange={(event) => onChange(event.target.value)}
          onBlur={onBlur}
          className={INPUT}
        />
        <button
          type="button"
          aria-pressed={shown}
          aria-controls={id}
          onClick={() => setShown((s) => !s)}
          className="inline-flex min-h-10 shrink-0 items-center whitespace-nowrap rounded-lg border border-slate-300 bg-white px-3 text-sm font-semibold text-slate-800 transition-colors duration-200 ease-brand hover:border-brand-300 hover:bg-brand-50"
        >
          {shown ? hideLabel : showLabel}
        </button>
      </div>
    </FieldShell>
  );
}

/** M7c-P7 (M2): a plain check that a typed email looks like one; the API remains the judge. */
export function looksLikeEmail(value: string): boolean {
  return /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(value.trim());
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

/**
 * M7c-P7: a date or a time, as the browser's own control (accessible on phones, keyboard on
 * desktops; DESIGN.md §5). `value` is `YYYY-MM-DD` or `HH:MM` in the clinic's time zone, as the
 * API expects; the API still checks it.
 */
export function DateField(props: Omit<Parameters<typeof TextField>[0], "type" | "inputMode">) {
  return <TextField {...props} type="date" />;
}

export function TimeField(props: Omit<Parameters<typeof TextField>[0], "type" | "inputMode">) {
  return <TextField {...props} type="time" />;
}

/**
 * M7c-P7: the list of a form's errors at its top (DESIGN.md §5), each a link to its field, so a
 * keyboard or screen-reader user reaches the first problem at once. Give it a `ref` (or use
 * `useFocusOnError`) to move focus here after a failed submit.
 */
export function ErrorSummary({
  title = "Please correct these fields",
  errors,
  ref,
}: {
  title?: string;
  errors: readonly { readonly id: string; readonly message: string }[];
  ref?: Ref<HTMLDivElement>;
}) {
  if (errors.length === 0) return null;
  return (
    <div ref={ref} role="alert" tabIndex={-1} className="rounded-xl border border-danger-line bg-danger-soft p-4 text-slate-900">
      <p className="font-semibold text-danger">{title}</p>
      <ul className="mt-2 list-disc space-y-1 pl-5 text-sm">
        {errors.map((e) => (
          <li key={e.id}>
            <a href={`#${e.id}`} className="font-medium text-danger underline underline-offset-2">
              {e.message}
            </a>
          </li>
        ))}
      </ul>
    </div>
  );
}
