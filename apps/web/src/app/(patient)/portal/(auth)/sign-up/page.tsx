import type { Metadata } from "next";

import { PortalSignUpForm } from "@/features/portal/PortalSignUpForm";
import { safePortalNextPath } from "@/lib/auth/safe-next";
import { PORTAL_LANGUAGE_COOKIE, parsePortalLanguage } from "@/lib/i18n/portal";
import { cookies } from "next/headers";

export const metadata: Metadata = { title: "Create an account · MediEase for patients" };

type Query = Promise<Record<string, string | string[] | undefined>>;

export default async function PortalSignUpPage({ searchParams }: { searchParams: Query }) {
  const query = await searchParams;
  const next = Array.isArray(query.next) ? query.next[0] : query.next;
  const language = parsePortalLanguage((await cookies()).get(PORTAL_LANGUAGE_COOKIE)?.value);
  return <PortalSignUpForm next={safePortalNextPath(next)} language={language} />;
}
