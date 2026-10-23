"use client";

import { useRouter } from "next/navigation";
import { createContext, useCallback, useContext, useMemo, useState, type ReactNode } from "react";

import { TODAY_PATH, type Membership } from "@/features/auth/landing";

import {
  canSwitch,
  readRememberedWorkspace,
  rememberWorkspace,
  resolveWorkspace,
  type Workspace,
} from "./workspace";

export interface WorkspaceValue {
  readonly workspace: Workspace;
  /** A practising owner (FR-UX-06): may switch between Owner and Doctor. */
  readonly canSwitch: boolean;
  /** The member's own doctor profile here, if any. */
  readonly doctorId: string | null;
  /** Switch view (ignored unless allowed) and open that workspace's Today. */
  readonly switchTo: (workspace: Workspace) => void;
}

const WorkspaceContext = createContext<WorkspaceValue | null>(null);

/** The current workspace; outside a clinic workspace (tests of a lone screen), the role's own. */
export function useWorkspace(): WorkspaceValue | null {
  return useContext(WorkspaceContext);
}

/**
 * Holds the workspace for one clinic membership (M6a-P6, decision 1A). Re-mounted per clinic,
 * so another clinic's choice never leaks in. A view only: permissions come from the membership.
 */
export function WorkspaceProvider({ membership, children }: { membership: Membership; children: ReactNode }) {
  const router = useRouter();
  const [chosen, setChosen] = useState<Workspace>(() =>
    resolveWorkspace(membership, readRememberedWorkspace(membership.clinic_id)),
  );
  const switchable = canSwitch(membership);

  const switchTo = useCallback(
    (next: Workspace) => {
      if (!switchable || (next !== "OWNER" && next !== "DOCTOR")) return;
      rememberWorkspace(membership.clinic_id, next);
      setChosen(next);
      router.push(TODAY_PATH);
    },
    [switchable, membership.clinic_id, router],
  );

  const value = useMemo<WorkspaceValue>(
    () => ({
      workspace: switchable ? chosen : membership.role,
      canSwitch: switchable,
      doctorId: membership.doctor_id,
      switchTo,
    }),
    [switchable, chosen, membership.role, membership.doctor_id, switchTo],
  );
  return <WorkspaceContext.Provider value={value}>{children}</WorkspaceContext.Provider>;
}
