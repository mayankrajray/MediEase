import type { Metadata } from "next";

import { PlanPage } from "@/features/plan/PlanPage";

export const metadata: Metadata = { title: "Plan · MediEase" };

/** The clinic's plan, its use and the trial (M6d-P7, FR-SUB-01), owners only. */
export default function Plan() {
  return <PlanPage />;
}
