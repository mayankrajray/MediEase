import { ChevronRight } from "lucide-react";
import Link from "next/link";

/**
 * M7c-P7: where a nested screen sits ("Patients › Asha Rao › Visit"). The last item is the current
 * page (`aria-current="page"`, not a link); separators are decorative.
 */
export function Breadcrumbs({
  items,
  label = "Breadcrumb",
}: {
  items: readonly { readonly label: string; readonly href?: string }[];
  label?: string;
}) {
  return (
    <nav aria-label={label}>
      <ol className="flex flex-wrap items-center gap-1 text-sm text-slate-700">
        {items.map((item, index) => {
          const last = index === items.length - 1;
          return (
            <li key={`${item.label}-${index}`} className="inline-flex items-center gap-1">
              {last || item.href === undefined ? (
                <span aria-current={last ? "page" : undefined} className={last ? "font-medium text-slate-900" : undefined}>
                  {item.label}
                </span>
              ) : (
                <Link href={item.href} className="rounded underline-offset-4 hover:text-brand-800 hover:underline">
                  {item.label}
                </Link>
              )}
              {!last && <ChevronRight aria-hidden="true" className="size-4 text-slate-500" />}
            </li>
          );
        })}
      </ol>
    </nav>
  );
}
