import type { Metadata } from "next";

import { PortalSignUpForm } from "@/features/portal/PortalSignUpForm";
import { safePortalNextPath } from "@/lib/auth/safe-next";

export const metadata: Metadata = { title: "Create an account · MediEase for patients" };

type Query = Promise<Record<string, string | string[] | undefined>>;

export default async function PortalSignUpPage({ searchParams }: { searchParams: Query }) {
  const query = await searchParams;
  const next = Array.isArray(query.next) ? query.next[0] : query.next;
  return <PortalSignUpForm next={safePortalNextPath(next)} />;
}
