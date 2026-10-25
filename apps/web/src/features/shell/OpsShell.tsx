"use client";

import { useRouter } from "next/navigation";
import { useEffect, type ReactNode } from "react";

import { TODAY_PATH } from "@/features/auth/landing";
import { useSession } from "@/features/auth/SessionProvider";

import { RolePill, Shell, type ShellLink } from "./Shell";

type OpsRole = "OPS_ADMIN" | "OPS_REVIEWER";

// M6c-P2 (decision M3): each link for the ops role that can open it.
const OPS_LINKS: readonly (ShellLink & { readonly role: OpsRole | null })[] = [
  { href: "/ops", label: "Home", exact: true, role: null },
  { href: "/ops/applications", label: "Applications", role: "OPS_REVIEWER" },
  { href: "/ops/messaging-costs", label: "Messaging costs", role: "OPS_ADMIN" },
];

/**
 * The ops console frame (platform staff only, spec R10) on the shared `Shell` (M6-P2 decision
 * 7A). Clinic staff who land here are sent to Today (M6-P1). The screens are the clinics list,
 * the Create clinic wizard (M1-P7), the monthly messaging costs (M5-P6) and the review of
 * clinic applications (M6c-P2).
 */
export function OpsShell({ children }: { children: ReactNode }) {
  const router = useRouter();
  const { identity } = useSession();
  const allowed = identity.user.is_platform_ops;
  const roles: readonly string[] = identity.user.ops_roles;
  const links = OPS_LINKS.filter((link) => link.role === null || roles.includes(link.role));

  useEffect(() => {
    if (!allowed) router.replace(TODAY_PATH);
  }, [allowed, router]);

  if (!allowed) {
    return null;
  }

  return (
    <Shell navLabel="Ops" links={links} person={identity.user.full_name} identity={<RolePill>Ops console</RolePill>}>
      {children}
    </Shell>
  );
}
