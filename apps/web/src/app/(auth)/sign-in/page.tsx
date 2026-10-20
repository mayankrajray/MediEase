import type { Metadata } from "next";

import { parseSignInReason } from "@/features/auth/messages";
import { SignInForm } from "@/features/auth/SignInForm";
import { TODAY_PATH } from "@/features/auth/landing";
import { safeNextPath } from "@/lib/auth/safe-next";

export const metadata: Metadata = { title: "Sign in · MediEase" };

type Query = Promise<Record<string, string | string[] | undefined>>;

function first(value: string | string[] | undefined): string | undefined {
  return Array.isArray(value) ? value[0] : value;
}

/**
 * `?next=` (where the person was headed) and `?reason=` (why they are here) come
 * from the URL, so both are validated here before the form sees them.
 */
export default async function SignInPage({ searchParams }: { searchParams: Query }) {
  const query = await searchParams;
  const reason = parseSignInReason(first(query.reason));
  return (
    <SignInForm
      next={safeNextPath(first(query.next), TODAY_PATH)}
      {...(reason === undefined ? {} : { reason })}
    />
  );
}
