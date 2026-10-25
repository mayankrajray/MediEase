import type { Metadata } from "next";

import { OpsHome } from "@/features/ops/OpsHome";

export const metadata: Metadata = { title: "Clinics · Ops · MediEase" };

export default function OpsHomePage() {
  // M6c-P1, P2: the clinics (OPS_ADMIN) and the applications waiting (OPS_REVIEWER).
  return <OpsHome />;
}
