"use client";

import { useId, useState } from "react";

import { cx } from "@/components/ui/cx";

import { WORKSPACE_LABELS, type Workspace } from "./workspace";

const OPTIONS: readonly Workspace[] = ["OWNER", "DOCTOR"];

/**
 * The practising owner's Owner | Doctor switch (FR-UX-06, decision 6A). A radio group: Tab
 * reaches it, the arrow keys move between the two, and the choice is announced. It changes the
 * view (navigation, Today, "mine") and never what the owner may do.
 */
export function WorkspaceSwitch({
  workspace,
  onSwitch,
}: {
  workspace: Workspace;
  onSwitch: (workspace: Workspace) => void;
}) {
  const name = useId();
  const [announced, setAnnounced] = useState("");

  function choose(next: Workspace) {
    if (next === workspace) return;
    setAnnounced(`${WORKSPACE_LABELS[next]} view`);
    onSwitch(next);
  }

  return (
    <fieldset className="flex items-center">
      <legend className="sr-only">View</legend>
      <div className="inline-flex rounded-lg border border-slate-300 bg-slate-50 p-0.5">
        {OPTIONS.map((option) => {
          const checked = option === workspace;
          return (
            <label
              key={option}
              className={cx(
                "relative cursor-pointer rounded-md px-3 py-1 text-sm font-medium transition-colors motion-reduce:transition-none has-[:focus-visible]:outline has-[:focus-visible]:outline-2 has-[:focus-visible]:outline-brand-700",
                checked ? "bg-white text-brand-900 shadow-sm ring-1 ring-brand-200" : "text-slate-700 hover:bg-white",
              )}
            >
              <input
                type="radio"
                name={name}
                value={option}
                checked={checked}
                onChange={() => choose(option)}
                className="sr-only"
              />
              {WORKSPACE_LABELS[option]}
            </label>
          );
        })}
      </div>
      <span role="status" className="sr-only">
        {announced}
      </span>
    </fieldset>
  );
}
