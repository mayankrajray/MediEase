import { cx } from "./cx";

/**
 * A grey placeholder where content will appear. Decorative (`aria-hidden`): the screen that shows
 * it also says "Loading…" in a `role="status"`, so a screen reader hears words, not shapes. The
 * pulse stops for people who ask for less motion.
 */
export function Skeleton({ className }: { className?: string }) {
  return <div aria-hidden="true" className={cx("animate-pulse rounded-lg bg-slate-200 motion-reduce:animate-none", className)} />;
}

/**
 * M7c-P7 (M5): loading rows for a section that already sits in a card (no second surface), with
 * its `role="status"` words.
 */
export function RowsSkeleton({ label, rows = 2 }: { label: string; rows?: number }) {
  return (
    <div>
      <p role="status" className="sr-only">
        {label}
      </p>
      <div aria-hidden="true" className="space-y-2">
        {Array.from({ length: rows }, (_, i) => (
          <Skeleton key={i} className="h-11" />
        ))}
      </div>
    </div>
  );
}

/**
 * M7c-P7 (M4): the loading state of a list or table (DESIGN.md §8a): rows shaped like the content
 * on the list's own surface, and a `role="status"` line saying what is loading. Pass `label=""`
 * when the screen's `StatusMessage` already says it.
 */
export function ListSkeleton({ label, rows = 4 }: { label: string; rows?: number }) {
  return (
    <div>
      {label !== "" && (
        <p role="status" className="sr-only">
          {label}
        </p>
      )}
      <div aria-hidden="true" className="overflow-hidden rounded-card border border-line bg-surface shadow-card">
        {Array.from({ length: rows }, (_, i) => (
          <div key={i} className={cx("flex items-center gap-4 px-4 py-3.5", i > 0 && "border-t border-line")}>
            <Skeleton className="h-5 w-20" />
            <Skeleton className="h-5 flex-1" />
            <Skeleton className="hidden h-5 w-28 sm:block" />
            <Skeleton className="h-8 w-24" />
          </div>
        ))}
      </div>
    </div>
  );
}
