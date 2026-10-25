"use client";

import { useSession } from "@/features/auth/SessionProvider";

import { ApplicationsWaiting } from "./ApplicationsWaiting";
import { ClinicList } from "./ClinicList";

/**
 * The ops home (M6c-P2, decision M3): the clinics for OPS_ADMIN, the applications waiting for
 * OPS_REVIEWER, both for a user who holds both roles. The API enforces each; this only avoids
 * showing a screen the user cannot open.
 */
export function OpsHome() {
  const { identity } = useSession();
  const roles = identity.user.ops_roles;
  return (
    <div className="space-y-8">
      {roles.includes("OPS_ADMIN") && <ClinicList />}
      {roles.includes("OPS_REVIEWER") && <ApplicationsWaiting />}
    </div>
  );
}
