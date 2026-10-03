import type { ReactNode } from "react";

import { WorkspaceGuard } from "@/features/shell/WorkspaceGuard";

/** Pages that need a working clinic: framed in the dashboard shell. */
export default function WorkspaceLayout({ children }: Readonly<{ children: ReactNode }>) {
  return <WorkspaceGuard>{children}</WorkspaceGuard>;
}
