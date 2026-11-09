import { cx } from "./cx";

/**
 * M7c-P7 (M4): a small set of mutually exclusive views of one list ("Open" | "Answered"), as
 * toggle buttons in a named group (`aria-pressed` says which is on). For views that swap the
 * whole page use `Tabs`; for a form value use radios. The look matches `Tabs`.
 */
export function Segmented<T extends string>({
  label,
  options,
  value,
  onChange,
}: {
  label: string;
  options: readonly { readonly value: T; readonly label: string }[];
  value: T;
  onChange: (value: T) => void;
}) {
  return (
    <div role="group" aria-label={label} className="inline-flex gap-1 rounded-lg border border-line bg-surface p-1 shadow-card">
      {options.map((o) => {
        const on = o.value === value;
        return (
          <button
            key={o.value}
            type="button"
            aria-pressed={on}
            onClick={() => onChange(o.value)}
            className={cx(
              "min-h-9 rounded-md px-3 font-medium transition-colors duration-200 ease-brand motion-reduce:transition-none",
              on ? "bg-brand-700 text-white" : "text-slate-700 hover:bg-slate-100 hover:text-slate-900",
            )}
          >
            {o.label}
          </button>
        );
      })}
    </div>
  );
}
