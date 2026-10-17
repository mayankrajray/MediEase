import type { Metadata } from "next";

import { PatientResults } from "@/features/patients/PatientResults";

// No patient data in the title or metadata (apps/web/CLAUDE.md).
export const metadata: Metadata = { title: "Patients · MediEase" };

/** `/patients?q=` shows the matches for a lookup text; the text itself stays out of the title. */
export default async function PatientsPage({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const { q } = await searchParams;
  const text = (Array.isArray(q) ? q[0] : q) ?? "";
  return <PatientResults key={text} q={text.slice(0, 200)} />;
}
