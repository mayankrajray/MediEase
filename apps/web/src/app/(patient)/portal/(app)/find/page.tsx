import type { Metadata } from "next";

import { FindADoctor } from "@/features/portal/FindADoctor";

export const metadata: Metadata = { title: "Find a doctor · MediEase for patients" };

/** *Find a doctor* until directory search (M6c) (M6b-P2 decision 4A, spec R16). */
export default function PortalFindPage() {
  return <FindADoctor />;
}