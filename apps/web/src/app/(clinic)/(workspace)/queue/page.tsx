import type { Metadata } from "next";

import { QueueBoard } from "@/features/queue/QueueBoard";

export const metadata: Metadata = { title: "Queue · MediEase" };

/** `?book=1` or `?walk-in=1` (Today's quick actions, M6a-P6) open that drawer once loaded. */
export default async function QueuePage({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const params = await searchParams;
  const overlay = params["book"] !== undefined ? "book" : params["walk-in"] !== undefined ? "walk-in" : undefined;
  return <QueueBoard {...(overlay === undefined ? {} : { initialOverlay: overlay })} />;
}
