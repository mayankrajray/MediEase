"use client";

import { useRouter } from "next/navigation";
import { useEffect, type ReactNode } from "react";

import { TODAY_PATH } from "@/features/auth/landing";
import { useSession } from "@/features/auth/SessionProvider";

import { RolePill, Shell, type ShellLink } from "./Shell";

const OPS_LINKS: readonly ShellLink[] = [
  { href: "/ops", label: "Clinics", exact: true },
  { href: "/ops/messaging-costs", label: "Messaging costs" },
];

/**
 * The ops console frame (platform staff only, spec R10) on the shared `Shell` (M6-P2 decision
 * 7A). Clinic staff who land here are sent to Today (M6-P1). The screens are the clinics list,
 * the Create clinic wizard (M1-P7) and the monthly messaging costs (M5-P6).
 */
export function OpsShell({ children }: { children: ReactNode }) {
  const router = useRouter();
  const { identity } = useSession();
  const allowed = identity.user.is_platform_ops;

  useEffect(() => {
    if (!allowed) router.replace(TODAY_PATH);
  }, [allowed, router]);

  if (!allowed) {
    return null;
  }

  return (
    <Shell navLabel="Ops" links={OPS_LINKS} person={identity.user.full_name} identity={<RolePill>Ops console</RolePill>}>
      {children}
    </Shell>
  );
}
