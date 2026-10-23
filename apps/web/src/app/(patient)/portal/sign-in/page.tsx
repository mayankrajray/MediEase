import type { Metadata } from "next";

import { parsePortalReason } from "@/features/portal/messages";
import { PortalSignInForm } from "@/features/portal/PortalSignInForm";
import { safePortalNextPath } from "@/lib/auth/safe-next";

export const metadata: Metadata = { title: "Sign in · MediEase for patients" };

type Query = Promise<Record<string, string | string[] | undefined>>;

function first(value: string | string[] | undefined): string | undefined {
  return Array.isArray(value) ? value[0] : value;
}

/** `?next=` stays inside the portal and `?reason=` is allow-listed, before the form sees them. */
export default async function PortalSignInPage({ searchParams }: { searchParams: Query }) {
  const query = await searchParams;
  const reason = parsePortalReason(first(query.reason));
  return (
    <PortalSignInForm
      next={safePortalNextPath(first(query.next))}
      {...(reason === undefined ? {} : { reason })}
    />
  );
}
