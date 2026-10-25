import type { Metadata } from "next";

import { ReviewQueue } from "@/features/ops/reviewer/ReviewQueue";

export const metadata: Metadata = { title: "Applications · Ops · MediEase" };

/** M6c-P2: the reviewer's queue (OPS_REVIEWER; the API enforces it). */
export default function OpsApplicationsPage() {
  return <ReviewQueue />;
}
