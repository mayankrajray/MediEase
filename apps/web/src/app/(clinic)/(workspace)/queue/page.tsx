import type { Metadata } from "next";

import { QueueBoard } from "@/features/queue/QueueBoard";

export const metadata: Metadata = { title: "Queue · MediEase" };

export default function QueuePage() {
  return <QueueBoard />;
}