import type { ReactNode } from "react";

import { AuthFrame } from "@/components/ui/AuthFrame";

/** Sign-in and invitations: a centred card under the brand (M6-P2, decision 8A). */
export default function AuthLayout({ children }: Readonly<{ children: ReactNode }>) {
  return <AuthFrame>{children}</AuthFrame>;
}
