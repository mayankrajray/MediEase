import { ChevronLeft, ChevronRight } from "lucide-react";

import { Button } from "./Button";

/**
 * M7c-P7: previous and next through a paged list, with the position in words ("Page 2 of 7").
 * The API decides the pages; this only asks for another one. With `total` unknown (cursor
 * paging), it says "Page 2" and `hasNext` decides the button.
 */
export function Pagination({
  page,
  total,
  hasNext,
  onPage,
  label = "Pages",
  busy = false,
}: {
  page: number;
  total?: number;
  hasNext?: boolean;
  onPage: (page: number) => void;
  label?: string;
  busy?: boolean;
}) {
  const more = hasNext ?? (total !== undefined && page < total);
  return (
    <nav aria-label={label} className="flex flex-wrap items-center justify-between gap-3">
      <p className="text-sm text-slate-700" aria-live="polite">
        {total === undefined ? `Page ${page}` : `Page ${page} of ${total}`}
      </p>
      <div className="flex gap-2">
        <Button size="sm" disabled={page <= 1 || busy} onClick={() => onPage(page - 1)} icon={<ChevronLeft className="size-4" />}>
          Previous
        </Button>
        <Button size="sm" disabled={!more || busy} onClick={() => onPage(page + 1)}>
          Next
          <ChevronRight aria-hidden="true" className="size-4" />
        </Button>
      </div>
    </nav>
  );
}
