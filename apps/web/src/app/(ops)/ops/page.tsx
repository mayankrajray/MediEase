import type { Metadata } from "next";

import { ApplicationsWaiting } from "@/features/ops/ApplicationsWaiting";
import { ClinicList } from "@/features/ops/ClinicList";

export const metadata: Metadata = { title: "Clinics · Ops · MediEase" };

export default function OpsHomePage() {
  // M6c-P1: confirmed clinic applications waiting for MediEase, under the clinics.
  return (
    <div className="space-y-8">
      <ClinicList />
      <ApplicationsWaiting />
    </div>
  );
}
