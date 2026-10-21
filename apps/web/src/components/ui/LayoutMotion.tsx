"use client";

import { LazyMotion } from "motion/react";
import type { ReactNode } from "react";

const loadDomMax = () => import("./motion-max").then((module) => module.default);

/**
 * Layout animation for a list (M6-P2, decision 4A): inside it, `m.*` elements with `layout`
 * glide to their new place when the list reorders (a patient's status changed), and new ones
 * rise in. The extra features load on first use, in their own chunk; until then the list simply
 * renders. Reduced motion is honoured by the `MotionConfig` of the surrounding `MotionProvider`.
 */
export function LayoutMotion({ children }: { children: ReactNode }) {
  return (
    <LazyMotion features={loadDomMax} strict>
      {children}
    </LazyMotion>
  );
}

/** Props for a list item that glides when its list reorders and rises in when it is new. */
export const LIST_ITEM = {
  layout: "position",
  initial: { opacity: 0, y: 6 },
  animate: { opacity: 1, y: 0 },
  transition: { duration: 0.22, ease: "easeOut" },
} as const;
