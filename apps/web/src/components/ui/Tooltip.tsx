"use client";

import * as RadixTooltip from "@radix-ui/react-tooltip";
import type { ReactElement, ReactNode } from "react";

/**
 * M7c-P7: a short hint on hover and keyboard focus, on `@radix-ui/react-tooltip` (it names the
 * trigger for screen readers through `aria-describedby`, and Escape closes it). A tooltip adds
 * detail only: the trigger keeps its own accessible name, and nothing essential lives only here
 * (it cannot be reached on a touch screen). `children` must be one focusable element.
 */
export function Tooltip({
  content,
  children,
  side = "top",
}: {
  content: ReactNode;
  children: ReactElement;
  side?: "top" | "right" | "bottom" | "left";
}) {
  return (
    <RadixTooltip.Provider delayDuration={300}>
      <RadixTooltip.Root>
        <RadixTooltip.Trigger asChild>{children}</RadixTooltip.Trigger>
        <RadixTooltip.Portal>
          <RadixTooltip.Content
            side={side}
            sideOffset={6}
            className="z-50 max-w-xs rounded-lg bg-slate-900 px-3 py-1.5 text-sm text-white shadow-pop"
          >
            {content}
            <RadixTooltip.Arrow className="fill-slate-900" />
          </RadixTooltip.Content>
        </RadixTooltip.Portal>
      </RadixTooltip.Root>
    </RadixTooltip.Provider>
  );
}
