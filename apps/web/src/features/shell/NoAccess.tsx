"use client";

import { useSession } from "@/features/auth/SessionProvider";

import { SignOutButton } from "./SignOutButton";

/** Signed in, but with no active clinic membership (for example after being deactivated from the last one). */
export function NoAccess() {
  const { identity } = useSession();
  return (
    <main className="mx-auto max-w-xl space-y-4 p-6">
      <h1 className="text-2xl font-bold">No clinic access yet</h1>
      <p>
        {identity.user.full_name}, you are signed in, but you are not a member of any clinic. Ask your
        clinic owner to invite you, or contact MediEase support.
      </p>
      <SignOutButton />
    </main>
  );
}
