import type { Metadata } from "next";

import { PortalAccount } from "@/features/portal/PortalAccount";

export const metadata: Metadata = { title: "Your account · MediEase" };

/** The signed-in patient's account (M6a-P3). The proxy sends a signed-out visitor to sign in. */
export default function PortalPage() {
  return <PortalAccount />;
}
