import type { Metadata } from "next";

import { PortalMedicines } from "@/features/portal/Medicines";

export const metadata: Metadata = { title: "My medicines · MediEase for patients" };

/** *My medicines* (M6b-P3; spec R36, R37). */
export default function PortalMedicinesPage() {
  return <PortalMedicines />;
}