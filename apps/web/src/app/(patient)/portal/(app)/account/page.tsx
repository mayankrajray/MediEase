import type { Metadata } from "next";

import { PortalAccountPage } from "@/features/portal/PortalAccountPage";

export const metadata: Metadata = { title: "Account · MediEase for patients" };

/** *Account* (M6b-P2; spec R20, R21). */
export default function PortalAccountRoute() {
  return <PortalAccountPage />;
}