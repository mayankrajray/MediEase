import type { Metadata } from "next";

import { Home } from "@/features/portal/Home";

export const metadata: Metadata = { title: "MediEase for patients" };

/** *Home* (M6b-P2; FR-PRT-05, spec R16, R17). */
export default function PortalHomePage() {
  return <Home />;
}