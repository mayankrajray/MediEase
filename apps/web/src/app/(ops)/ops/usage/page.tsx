import type { Metadata } from "next";

import { ClinicUsage } from "@/features/ops/ClinicUsage";

export const metadata: Metadata = { title: "Clinic usage · Ops · MediEase" };

export default function OpsUsagePage() {
  return <ClinicUsage />;
}
