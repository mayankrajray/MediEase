import type { ReactNode } from "react";

import { BRAND_FONT } from "@/app/fonts";
import { AuthFrame } from "@/components/ui/AuthFrame";
import { RegisterServiceWorker } from "@/features/pwa/RegisterServiceWorker";
import { PWA_METADATA, PWA_VIEWPORT } from "@/lib/pwa/manifest";

// M7e-E1: the installable app's manifest link and iPhone tags (src/lib/pwa/manifest.ts).
export const metadata = PWA_METADATA;
export const viewport = PWA_VIEWPORT;

/** Sign-in and invitations: a centred card under the brand (M6-P2, decision 8A); brand font (M7c-P7). */
export default function AuthLayout({ children }: Readonly<{ children: ReactNode }>) {
  return (
    <div className={BRAND_FONT}>
      <AuthFrame>{children}</AuthFrame>
      <RegisterServiceWorker />
    </div>
  );
}
