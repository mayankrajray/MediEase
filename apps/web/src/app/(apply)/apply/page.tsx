import type { Metadata } from "next";

import { ApplyForm } from "@/features/apply/ApplyForm";

export const metadata: Metadata = {
  title: "Apply to join · MediEase",
  robots: { index: false, follow: false },
};

/** Applying to join MediEase (M6c-P1; FR-ONB-01, spec clinic-onboarding R1-R8, R23). */
export default function ApplyPage() {
  return <ApplyForm />;
}
