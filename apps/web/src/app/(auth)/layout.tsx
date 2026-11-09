import type { ReactNode } from "react";

import { BRAND_FONT } from "@/app/fonts";
import { AuthFrame } from "@/components/ui/AuthFrame";

/** Sign-in and invitations: a centred card under the brand (M6-P2, decision 8A); brand font (M7c-P7). */
export default function AuthLayout({ children }: Readonly<{ children: ReactNode }>) {
  return (
    <div className={BRAND_FONT}>
      <AuthFrame>{children}</AuthFrame>
    </div>
  );
}
