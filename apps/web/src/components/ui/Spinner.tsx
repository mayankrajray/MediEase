import { cx } from "./cx";

/**
 * A small turning ring for a wait inside a button or under a second (DESIGN.md §5: longer waits
 * show skeletons). Decorative: the control around it says what is happening in words.
 */
export function Spinner({ className }: { className?: string }) {
  return (
    <svg
      aria-hidden="true"
      viewBox="0 0 24 24"
      className={cx("size-4 shrink-0 animate-spin motion-reduce:animate-none", className)}
      fill="none"
    >
      <circle cx="12" cy="12" r="9" stroke="currentColor" strokeOpacity="0.25" strokeWidth="3" />
      <path d="M21 12a9 9 0 0 0-9-9" stroke="currentColor" strokeWidth="3" strokeLinecap="round" />
    </svg>
  );
}
