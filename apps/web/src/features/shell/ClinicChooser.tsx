"use client";

import { useRouter } from "next/navigation";
import { useEffect } from "react";

import { AuthFrame } from "@/components/ui/AuthFrame";
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
 * to make are sent on: ops to the console, everyone else to Today. M6-P2: the sign-in card frame.
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
    <AuthFrame>
    <div className="space-y-5 p-6">
      <h1 className="text-2xl font-bold tracking-tight">Choose a clinic</h1>
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
              className="w-full rounded-lg border border-slate-300 px-4 py-3 text-left transition-colors hover:border-brand-600 hover:bg-brand-50 motion-reduce:transition-none aria-[current=true]:border-2 aria-[current=true]:border-brand-700"
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
    </div>
    </AuthFrame>
  );
}
