import type { Metadata } from "next";

import { MyPatients } from "@/features/patients/MyPatients";

// No patient data in the title or metadata (apps/web/CLAUDE.md).
export const metadata: Metadata = { title: "My patients · MediEase" };

export default function MyPatientsPage() {
  return <MyPatients />;
}
