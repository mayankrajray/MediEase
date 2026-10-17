import type { Metadata } from "next";

import { PatientProfile } from "@/features/patients/PatientProfile";

// The title never names the patient (apps/web/CLAUDE.md).
export const metadata: Metadata = { title: "Patient · MediEase" };

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

/** One patient. A path that is not an ID is looked up as the nil ID, so it reads like any unknown patient. */
export default async function PatientPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return <PatientProfile key={id} patientId={UUID.test(id) ? id : "00000000-0000-0000-0000-000000000000"} />;
}
