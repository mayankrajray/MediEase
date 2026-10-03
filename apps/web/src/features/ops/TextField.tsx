"use client";

import type { HTMLInputAutoCompleteAttribute, HTMLInputTypeAttribute } from "react";

/**
 * A labelled text input with its hint and its own error. The error is linked with
 * `aria-describedby` and marks the input `aria-invalid`, and it is text, so state
 * is never carried by colour alone (apps/web/CLAUDE.md).
 */
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
}: {
  id: string;
  label: string;
  value: string;
  onChange: (value: string) => void;
  error?: string | undefined;
  hint?: string;
  required?: boolean;
  type?: HTMLInputTypeAttribute;
  autoComplete?: HTMLInputAutoCompleteAttribute;
  maxLength?: number;
  inputMode?: "text" | "numeric" | "tel" | "email";
}) {
  const hintId = `${id}-hint`;
  const errorId = `${id}-error`;
  const describedBy = [hint !== undefined ? hintId : null, error !== undefined ? errorId : null]
    .filter((part) => part !== null)
    .join(" ");

  return (
    <div className="space-y-1">
      <label htmlFor={id} className="block font-medium">
        {label}
        {required && <span className="text-slate-700"> (required)</span>}
      </label>
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
        aria-describedby={describedBy === "" ? undefined : describedBy}
        onChange={(event) => onChange(event.target.value)}
        className="w-full rounded border border-slate-500 px-3 py-2"
      />
      {hint !== undefined && (
        <p id={hintId} className="text-sm text-slate-700">
          {hint}
        </p>
      )}
      {error !== undefined && (
        <p id={errorId} className="text-sm font-medium text-red-900">
          {error}
        </p>
      )}
    </div>
  );
}
