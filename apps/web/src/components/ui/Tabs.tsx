"use client";

import * as RadixTabs from "@radix-ui/react-tabs";
import type { ReactNode } from "react";

/**
 * Tabs on the Radix headless primitive (M6-P1, decision 2 as amended: our look, a headless
 * primitive where the interaction is worth not re-implementing). Radix gives the WAI-ARIA tabs
 * pattern: `tablist`, `tab` and `tabpanel` wired to each other, roving focus, arrow keys, Home and
 * End, and automatic activation. Only the styling is ours.
 */
export interface TabItem {
  readonly value: string;
  readonly label: string;
  readonly content: ReactNode;
}

export function Tabs({
  label,
  items,
  defaultValue,
}: {
  /** Names the tab list for screen readers ("Today's views"). */
  label: string;
  items: readonly TabItem[];
  defaultValue?: string;
}) {
  return (
    <RadixTabs.Root defaultValue={defaultValue ?? items[0]?.value}>
      <RadixTabs.List
        aria-label={label}
        className="mb-4 inline-flex gap-1 rounded-lg border border-slate-200 bg-white p-1 shadow-card"
      >
        {items.map((item) => (
          <RadixTabs.Trigger
            key={item.value}
            value={item.value}
            className="min-h-9 rounded-md px-3 py-1.5 font-medium text-slate-700 transition-colors hover:bg-slate-100 motion-reduce:transition-none data-[state=active]:bg-brand-700 data-[state=active]:text-white"
          >
            {item.label}
          </RadixTabs.Trigger>
        ))}
      </RadixTabs.List>
      {items.map((item) => (
        <RadixTabs.Content key={item.value} value={item.value} className="focus-visible:outline-offset-4">
          {item.content}
        </RadixTabs.Content>
      ))}
    </RadixTabs.Root>
  );
}
