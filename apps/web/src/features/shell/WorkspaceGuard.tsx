"use client";

import { usePathname, useRouter } from "next/navigation";
import { useEffect, type ReactNode } from "react";

import { OPS_PATH, SELECT_CLINIC_PATH } from "@/features/auth/landing";
import { useSession } from "@/features/auth/SessionProvider";

import { AppShell } from "./AppShell";
import { ClinicGate } from "./ClinicGate";
import { NoAccess } from "./NoAccess";

/**
 * Guards the clinic workspace: ops users belong in the ops console (R10), a
 * person with several clinics and no working one must choose first, and a person
 * with none sees why. Otherwise it frames the page in the shell and loads the
 * clinic. UI routing only: the API enforces all of it again on every request.
 */
export function WorkspaceGuard({ children }: { children: ReactNode }) {
  const router = useRouter();
  const pathname = usePathname();
  const { identity, clinic } = useSession();

  const destination = identity.user.is_platform_ops
    ? OPS_PATH
    : clinic.kind === "choose"
      ? `${SELECT_CLINIC_PATH}?next=${encodeURIComponent(pathname)}`
      : null;

  useEffect(() => {
    if (destination !== null) {
      router.replace(destination);
    }
  }, [destination, router]);

  if (destination !== null || clinic.kind === "choose") {
    return null;
  }
  if (clinic.kind === "none") {
    return <NoAccess />;
  }
  return (
    <ClinicGate
      key={clinic.membership.clinic_id}
      membership={clinic.membership}
      sendClinicHeader={clinic.sendClinicHeader}
      frame={(body) => <AppShell membership={clinic.membership}>{body}</AppShell>}
    >
      {children}
    </ClinicGate>
  );
}
