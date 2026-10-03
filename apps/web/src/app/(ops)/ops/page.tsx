import type { Metadata } from "next";

import { ClinicList } from "@/features/ops/ClinicList";

export const metadata: Metadata = { title: "Clinics · Ops · MediEase" };

export default function OpsHomePage() {
  return <ClinicList />;
}
