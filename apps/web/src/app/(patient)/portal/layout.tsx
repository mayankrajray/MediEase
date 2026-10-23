import type { ReactNode } from "react";

import { AuthFrame } from "@/components/ui/AuthFrame";

/**
 * The patient portal's frame (M6a-P3): the same centred card as staff sign-in, with words for
 * patients. No staff `SessionProvider` here: the portal has its own session (ADR-0015).
 */
export default function PortalLayout({ children }: Readonly<{ children: ReactNode }>) {
  return <AuthFrame tagline="Your appointments and prescriptions, in one place">{children}</AuthFrame>;
}
