import type { Metadata } from "next";

import { MyAppointments } from "@/features/portal/MyAppointments";

export const metadata: Metadata = { title: "My appointments · MediEase for patients" };

/** *My appointments* (M6b-P2; FR-PRT-07, spec R18). */
export default function PortalAppointmentsPage() {
  return <MyAppointments />;
}