"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, type ReactNode } from "react";

import { QUEUE_PATH } from "@/features/auth/landing";
import { useSession } from "@/features/auth/SessionProvider";

import { SignOutButton } from "./SignOutButton";

/**
 * The ops console frame (platform staff only, spec R10). Clinic staff who land
 * here are sent to their queue. The screens are the clinics list and the Create
 * clinic wizard (M1-P7).
 */
export function OpsShell({ children }: { children: ReactNode }) {
  const router = useRouter();
  const { identity } = useSession();
  const allowed = identity.user.is_platform_ops;

  useEffect(() => {
    if (!allowed) router.replace(QUEUE_PATH);
  }, [allowed, router]);

  if (!allowed) {
    return null;
  }

  return (
    <div className="flex min-h-screen flex-col">
      <header className="border-b border-slate-300 bg-white">
        <div className="mx-auto flex max-w-6xl flex-wrap items-center justify-between gap-3 px-4 py-3">
          <div className="flex items-center gap-3">
            <span className="text-lg font-bold">MediEase</span>
            <span className="rounded bg-slate-100 px-2 py-0.5 text-sm ring-1 ring-inset ring-slate-400">
              Ops console
            </span>
          </div>
          <div className="flex items-center gap-3">
            <span>{identity.user.full_name}</span>
            <SignOutButton />
          </div>
        </div>
        <nav aria-label="Ops" className="mx-auto max-w-6xl px-4">
          <Link href="/ops" className="inline-block border-b-2 border-transparent py-2 font-semibold">
            Clinics
          </Link>
        </nav>
      </header>
      <main id="main" tabIndex={-1} className="mx-auto w-full max-w-6xl flex-1 p-4">
        {children}
      </main>
    </div>
  );
}
