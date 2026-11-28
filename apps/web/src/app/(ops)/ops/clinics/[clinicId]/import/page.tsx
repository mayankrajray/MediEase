import type { Metadata } from "next";
import { notFound } from "next/navigation";

import { PatientImport } from "@/features/ops/PatientImport";

export const metadata: Metadata = { title: "Import patients · Ops · MediEase" };

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

/** M9-P3: one clinic's patient list import. Anything that is not a clinic ID is a 404. */
export default async function ImportPatientsPage({ params }: { params: Promise<{ clinicId: string }> }) {
  const { clinicId } = await params;
  if (!UUID.test(clinicId)) notFound();
  return <PatientImport clinicId={clinicId} />;
}
