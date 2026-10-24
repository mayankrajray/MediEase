import type { ReactNode } from "react";

import { PortalShell } from "@/features/portal/PortalShell";

/** The signed-in patient portal (M6b-P2, decision 1A); the proxy sends signed-out visitors to sign in. */
export default function PortalAppLayout({ children }: Readonly<{ children: ReactNode }>) {
  return <PortalShell>{children}</PortalShell>;
}
