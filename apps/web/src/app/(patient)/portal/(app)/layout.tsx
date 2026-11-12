import type { ReactNode } from "react";

import { PortalShell } from "@/features/portal/PortalShell";
import { RegisterServiceWorker } from "@/features/pwa/RegisterServiceWorker";
import { PWA_METADATA, PWA_VIEWPORT } from "@/lib/pwa/manifest";

// M7e-E1: the installable app's manifest link and iPhone tags (src/lib/pwa/manifest.ts).
export const metadata = PWA_METADATA;
export const viewport = PWA_VIEWPORT;

/** The signed-in patient portal (M6b-P2, decision 1A); the proxy sends signed-out visitors to sign in. */
export default function PortalAppLayout({ children }: Readonly<{ children: ReactNode }>) {
  return (
    <>
      <PortalShell>{children}</PortalShell>
      {/* M7e-E1: the installable app's service worker. */}
      <RegisterServiceWorker />
    </>
  );
}