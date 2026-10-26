import type { Metadata } from "next";

import { FeeSchedulePage } from "@/features/fees/FeeSchedulePage";

export const metadata: Metadata = { title: "Fees · MediEase" };

/** The clinic's fee schedule (M6d-P1, FR-BIL-01): owners change it, everyone who bills reads it. */
export default function FeesPage() {
  return <FeeSchedulePage />;
}
