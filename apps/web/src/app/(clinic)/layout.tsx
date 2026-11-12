import type { ReactNode } from "react";

import { BRAND_FONT } from "@/app/fonts";
import { SessionProvider } from "@/features/auth/SessionProvider";
import { RegisterServiceWorker } from "@/features/pwa/RegisterServiceWorker";
import { PWA_METADATA, PWA_VIEWPORT } from "@/lib/pwa/manifest";

// M7e-E1: the installable app's manifest link and iPhone tags (src/lib/pwa/manifest.ts).
export const metadata = PWA_METADATA;
export const viewport = PWA_VIEWPORT;

/**
 * Everything under (clinic) needs a signed-in person. The provider asks the API
 * who that is (the session tokens are HttpOnly, and `me_access` is not sent on
 * page navigations), and sends anyone else to /sign-in. See M1-P6 design,
 * concept 2. M7c-P7: in the brand font.
 */
export default function ClinicLayout({ children }: Readonly<{ children: ReactNode }>) {
  return (
    <div className={BRAND_FONT}>
      <SessionProvider>{children}</SessionProvider>
      {/* M7e-E1: the installable app's service worker. */}
      <RegisterServiceWorker />
    </div>
  );
}
