"use client";

import { ChevronRight } from "lucide-react";
import { useRouter } from "next/navigation";
import { useEffect } from "react";

import { AuthFrame } from "@/components/ui/AuthFrame";
import { Avatar } from "@/components/ui/Avatar";
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
    <div className="space-y-6 p-6 sm:p-8">
      <div className="space-y-1">
        <h1 className="heading-5">Choose a clinic</h1>
        <p className="text-pretty text-slate-700">
          {identity.user.full_name}, you belong to more than one clinic. Pick the one you want to work in.
          You can switch at any time from the header.
        </p>
      </div>
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
              className="group flex w-full items-center gap-3 rounded-xl border border-line bg-surface px-4 py-3 text-left transition duration-200 ease-brand hover:-translate-y-px hover:border-brand-300 hover:bg-brand-50 hover:shadow-card motion-reduce:transition-none motion-reduce:hover:translate-y-0 aria-[current=true]:border-brand-700 aria-[current=true]:ring-1 aria-[current=true]:ring-brand-700"
            >
              <Avatar name={m.clinic_name} />
              <span className="min-w-0 flex-1">
                <span className="block truncate font-semibold text-slate-900">{m.clinic_name}</span>
                <span className="block text-sm text-slate-700">
                  {ROLE_LABELS[m.role]}
                  {STATUS_NOTE[m.clinic_status] !== undefined && ` · ${STATUS_NOTE[m.clinic_status]}`}
                  {m.clinic_id === activeId && " · current"}
                </span>
              </span>
              <ChevronRight aria-hidden="true" className="size-5 shrink-0 text-slate-500 transition-transform duration-200 ease-brand group-hover:translate-x-0.5" />
            </button>
          </li>
        ))}
      </ul>
      <SignOutButton />
    </div>
    </AuthFrame>
  );
}
