import type { ReactNode } from "react";

import { SessionProvider } from "@/features/auth/SessionProvider";
import { OpsShell } from "@/features/shell/OpsShell";

/** The ops console: platform staff only (spec R10). The API enforces it; this frames the screens. */
export default function OpsLayout({ children }: Readonly<{ children: ReactNode }>) {
  return (
    <SessionProvider>
      <OpsShell>{children}</OpsShell>
    </SessionProvider>
  );
}
