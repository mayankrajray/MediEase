import { Alert } from "./Alert";
import { cx } from "./cx";

/**
 * M7c-P7 (M4): the one polite live region of a screen (DESIGN.md §8a, "Feedback over silence").
 * It is always in the page, so screen readers announce what is put into it: while loading, the
 * words of `loading` (read, not shown, beside a skeleton); after an action, `message` as a success
 * notice naming what changed ("Asha Rao marked arrived at 10:42."). An empty message shows nothing.
 * Errors never go here: they are `ErrorNotice`s (`role="alert"`).
 */
export function StatusMessage({
  message,
  loading,
  tone = "success",
  className,
}: {
  message: string;
  /** Said while the screen loads, when there is no message to show. */
  loading?: string | undefined;
  tone?: "success" | "info";
  className?: string;
}) {
  return (
    <div role="status" aria-live="polite" className={cx(message === "" && "sr-only", className)}>
      {message !== "" ? (
        <Alert tone={tone} className="py-3">
          {message}
        </Alert>
      ) : (
        (loading ?? "")
      )}
    </div>
  );
}
