"use client";

import { useRouter } from "next/navigation";
import { useEffect } from "react";

import { ROLE_LABELS } from "@/features/auth/labels";
import { OPS_PATH, TODAY_PATH, type ClinicStatus } from "@/features/auth/landing";
import { useSession } from "@/features/auth/SessionProvider";

import { SignOutButton } from "./SignOutButton";

const STATUS_NOTE: Readonly<Partial<Record<ClinicStatus, string>>> = {
  ONBOARDING: "Setup in progress",
  SUSPENDED: "Suspended",
};

/**
 * The page a person with several clinics sees when no clinic is chosen yet.
 * `next` has already passed `safeNextPath` on the server. People with no choice
 * to make are sent on: ops to the console, everyone else to the queue.
 */
export function ClinicChooser({ next }: { next: string }) {
  const router = useRouter();
  const { identity, clinic, selectClinic } = useSession();

  const skip = identity.user.is_platform_ops
    ? OPS_PATH
    : identity.memberships.length < 2
      ? TODAY_PATH
      : null;

  useEffect(() => {
    if (skip !== null) router.replace(skip);
  }, [skip, router]);

  if (skip !== null) {
    return null;
  }

  const activeId = clinic.kind === "active" ? clinic.membership.clinic_id : undefined;

  return (
    <main className="mx-auto max-w-xl space-y-5 p-6">
      <h1 className="text-2xl font-bold">Choose a clinic</h1>
      <p>
        {identity.user.full_name}, you belong to more than one clinic. Pick the one you want to work in.
        You can switch at any time from the header.
      </p>
      <ul className="space-y-3">
        {identity.memberships.map((m) => (
          <li key={m.clinic_id}>
            <button
              type="button"
              aria-current={m.clinic_id === activeId ? "true" : undefined}
              onClick={() => {
                selectClinic(m.clinic_id);
                router.replace(next);
              }}
              className="w-full rounded border border-slate-500 px-4 py-3 text-left hover:bg-slate-50 aria-[current=true]:border-2 aria-[current=true]:border-blue-800"
            >
              <span className="block text-lg font-semibold">{m.clinic_name}</span>
              <span className="block text-slate-700">
                {ROLE_LABELS[m.role]}
                {STATUS_NOTE[m.clinic_status] !== undefined && ` · ${STATUS_NOTE[m.clinic_status]}`}
                {m.clinic_id === activeId && " · current"}
              </span>
            </button>
          </li>
        ))}
      </ul>
      <SignOutButton />
    </main>
  );
}
