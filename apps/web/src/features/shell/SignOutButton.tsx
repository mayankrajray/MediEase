"use client";

import { useState } from "react";

import { useSession } from "@/features/auth/SessionProvider";

/** Ends the session. Shows progress because the API call can take a moment. */
export function SignOutButton() {
  const { signOut } = useSession();
  const [pending, setPending] = useState(false);

  return (
    <button
      type="button"
      disabled={pending}
      onClick={() => {
        setPending(true);
        void signOut();
      }}
      className="rounded-lg border border-slate-400 px-3 py-1.5 hover:bg-slate-100 disabled:cursor-not-allowed disabled:text-slate-600"
    >
      {pending ? "Signing out…" : "Sign out"}
    </button>
  );
}
