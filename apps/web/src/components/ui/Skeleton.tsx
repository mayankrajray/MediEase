import { cx } from "./cx";

/**
 * A grey placeholder where content will appear. Decorative (`aria-hidden`): the screen that shows
 * it also says "Loading…" in a `role="status"`, so a screen reader hears words, not shapes. The
 * pulse stops for people who ask for less motion.
 */
export function Skeleton({ className }: { className?: string }) {
  return <div aria-hidden="true" className={cx("animate-pulse rounded-lg bg-slate-200 motion-reduce:animate-none", className)} />;
}
