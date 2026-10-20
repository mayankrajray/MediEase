"use client";

import { LazyMotion, MotionConfig, domAnimation, m, type Variants } from "motion/react";
import type { ReactNode } from "react";

/**
 * Motion for the clinic and ops screens (M6-P1, decision 3A). `LazyMotion` with the
 * `domAnimation` features loads only what animating, entering and gestures need, and `strict`
 * makes a stray full `motion.*` component an error, so the bundle stays small: use `m.*` inside.
 * `reducedMotion="user"` honours the system setting: with "reduce motion" on, things appear
 * without moving. Never mounted on the patient pages (`/p/…`, NFR-02's 200 KB budget).
 */
export function MotionProvider({ children }: { children: ReactNode }) {
  return (
    <LazyMotion features={domAnimation} strict>
      <MotionConfig reducedMotion="user">{children}</MotionConfig>
    </LazyMotion>
  );
}

/** A list whose items slide up into place one after another. */
export const STAGGER: Variants = {
  hidden: {},
  shown: { transition: { staggerChildren: 0.05 } },
};

export const RISE: Variants = {
  hidden: { opacity: 0, y: 8 },
  shown: { opacity: 1, y: 0, transition: { duration: 0.22, ease: "easeOut" } },
};

export { m };
