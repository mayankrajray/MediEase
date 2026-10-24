import type { Metadata } from "next";

import { PortalPrescriptions } from "@/features/portal/PortalPrescriptions";

export const metadata: Metadata = { title: "My prescriptions · MediEase for patients" };

/** *My prescriptions* (M6b-P2; spec R19). */
export default function PortalPrescriptionsPage() {
  return <PortalPrescriptions />;
}