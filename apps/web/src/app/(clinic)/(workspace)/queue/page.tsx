import type { Metadata } from "next";

import { QueueBoard } from "@/features/queue/QueueBoard";

export const metadata: Metadata = { title: "Queue · MediEase" };

const ISO_DAY = /^\d{4}-\d{2}-\d{2}$/;

/**
 * `?book=1` or `?walk-in=1` (Today's quick actions, M6a-P6) open that drawer once loaded.
 * `?date=YYYY-MM-DD` (a notification's link, M6a-P7) opens that day; anything else is ignored.
 * Keyed by the day, so following a second link while on the queue shows the new day.
 */
export default async function QueuePage({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const params = await searchParams;
  const overlay = params["book"] !== undefined ? "book" : params["walk-in"] !== undefined ? "walk-in" : undefined;
  const raw = params["date"];
  const date = typeof raw === "string" && ISO_DAY.test(raw) && !Number.isNaN(Date.parse(raw)) ? raw : undefined;
  return (
    <QueueBoard
      key={date ?? "today"}
      {...(overlay === undefined ? {} : { initialOverlay: overlay })}
      {...(date === undefined ? {} : { initialDate: date })}
    />
  );
}