import type { ReactNode } from "react";

import { BRAND_FONT } from "@/app/fonts";
import { SessionProvider } from "@/features/auth/SessionProvider";
import { RegisterServiceWorker } from "@/features/pwa/RegisterServiceWorker";
import { PWA_METADATA, PWA_VIEWPORT } from "@/lib/pwa/manifest";
import { OpsShell } from "@/features/shell/OpsShell";

// M7e-E1: the installable app's manifest link and iPhone tags (src/lib/pwa/manifest.ts).
export const metadata = PWA_METADATA;
export const viewport = PWA_VIEWPORT;

/** The ops console: platform staff only (spec R10). The API enforces it; this frames the screens. */
export default function OpsLayout({ children }: Readonly<{ children: ReactNode }>) {
  return (
    <div className={BRAND_FONT}>
      <SessionProvider>
        <OpsShell>{children}</OpsShell>
      </SessionProvider>
      <RegisterServiceWorker />
    </div>
  );
}
