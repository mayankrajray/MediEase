"use client";

import { useId } from "react";

import { addDays, formatDay } from "@/lib/format/time";

import type { AdviceText } from "./draft";

const BOXES: readonly { readonly key: keyof AdviceText; readonly label: string; readonly rows: number }[] = [
  { key: "diet", label: "Diet", rows: 2 },
  { key: "activity", label: "Activity", rows: 2 },
  { key: "return_if", label: "Come back immediately if", rows: 2 },
  { key: "notes", label: "Other advice", rows: 2 },
];
const SHORTCUTS = [3, 7, 14] as const;

/**
 * Prescription-level advice and the follow-up (FR-RX-03): diet, activity and "come back
 * immediately if…", one entry per line, and notes, all shown to the patient as written; the
 * follow-up date with +3, +7 and +14 day shortcuts from the clinic's today.
 */
export function AdviceEditor({
  advice,
  followUp,
  today,
  disabled,
  onAdvice,
  onFollowUp,
  onLeave,
}: Readonly<{
  advice: AdviceText;
  followUp: string;
  today: string;
  disabled: boolean;
  onAdvice: (advice: AdviceText) => void;
  onFollowUp: (date: string) => void;
  /** Leaving a field saves at once (decision 2A). */
  onLeave: () => void;
}>) {
  const base = useId();
  return (
    <div className="space-y-3">
      <div className="grid grid-cols-2 gap-3">
        {BOXES.map((box) => (
          <div key={box.key}>
            <label htmlFor={`${base}-${box.key}`} className="block font-medium">
              {box.label}
              {box.key !== "notes" && <span className="text-sm font-normal text-slate-700"> (one per line)</span>}
            </label>
            <textarea
              id={`${base}-${box.key}`}
              rows={box.rows}
              disabled={disabled}
              maxLength={box.key === "notes" ? 2000 : 3000}
              value={advice[box.key]}
              onChange={(e) => onAdvice({ ...advice, [box.key]: e.target.value })}
              onBlur={onLeave}
              className="w-full rounded border border-slate-500 px-2 py-1.5"
            />
          </div>
        ))}
      </div>
      <div className="flex flex-wrap items-end gap-2">
        <div>
          <label htmlFor={`${base}-follow-up`} className="block font-medium">
            Follow-up
          </label>
          <input
            id={`${base}-follow-up`}
            type="date"
            min={addDays(today, 1)}
            max={addDays(today, 365)}
            disabled={disabled}
            value={followUp}
            onChange={(e) => onFollowUp(e.target.value)}
            onBlur={onLeave}
            className="rounded border border-slate-500 px-2 py-1.5"
          />
        </div>
        {SHORTCUTS.map((days) => (
          <button
            key={days}
            type="button"
            disabled={disabled}
            aria-label={`Follow-up in ${days} days`}
            onClick={() => onFollowUp(addDays(today, days))}
            className="rounded border border-slate-600 px-3 py-1.5 font-medium hover:bg-slate-100 disabled:text-slate-500"
          >
            +{days} d
          </button>
        ))}
        {followUp !== "" && (
          <button
            type="button"
            disabled={disabled}
            onClick={() => onFollowUp("")}
            className="rounded border border-slate-600 px-3 py-1.5 font-medium hover:bg-slate-100 disabled:text-slate-500"
          >
            No follow-up
          </button>
        )}
        {followUp !== "" && <p className="pb-2 text-slate-800">{formatDay(followUp)}</p>}
      </div>
    </div>
  );
}
