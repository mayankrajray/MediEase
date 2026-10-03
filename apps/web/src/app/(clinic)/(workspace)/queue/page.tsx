import type { Metadata } from "next";

import { EmptyQueue } from "@/features/shell/EmptyQueue";

export const metadata: Metadata = { title: "Queue · MediEase" };

export default function QueuePage() {
  return <EmptyQueue />;
}
