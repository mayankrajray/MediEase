"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import type { ReactNode } from "react";

import { ROLE_LABELS } from "@/features/auth/labels";
import type { Membership } from "@/features/auth/landing";
import { useSession } from "@/features/auth/SessionProvider";
import { PatientSearch } from "@/features/patients/PatientSearch";
import {
  RegisterPatientProvider,
  useRegisterPatient,
} from "@/features/patients/RegisterPatientProvider";

import { useOptionalClinic } from "./ClinicGate";
import { ClinicSwitcher } from "./ClinicSwitcher";
import { visibleNav } from "./nav";
import { SignOutButton } from "./SignOutButton";

/**
 * The clinic dashboard frame: who and where you are, the switcher for people in
 * several clinics, navigation, and sign-out. Designed for a 1366x768 front-desk
 * screen and keyboard use (apps/web/CLAUDE.md). Shows the person's name and
 * role, never their phone number or email. Once the clinic has loaded, roles that
 * manage patients get the patient search (`/`) and Register patient in the header.
 */
export function AppShell({ membership, children }: { membership: Membership; children: ReactNode }) {
  const { identity, selectClinic } = useSession();
  const pathname = usePathname();
  const clinicReady = useOptionalClinic() !== null;
  const managesPatients = membership.permissions.includes("PATIENTS_MANAGE");

  return (
    <RegisterPatientProvider enabled={managesPatients}>
    <div className="flex min-h-screen flex-col">
      <a
        href="#main"
        className="sr-only focus:not-sr-only focus:absolute focus:left-2 focus:top-2 focus:bg-white focus:p-2"
      >
        Skip to content
      </a>

      <header className="border-b border-slate-300 bg-white">
        <div className="mx-auto flex max-w-6xl flex-wrap items-center justify-between gap-x-6 gap-y-2 px-4 py-3">
          <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
            <span className="text-lg font-bold">MediEase</span>
            {identity.memberships.length > 1 ? (
              <ClinicSwitcher
                memberships={identity.memberships}
                activeClinicId={membership.clinic_id}
                onSelect={selectClinic}
              />
            ) : (
              <span className="font-medium">{membership.clinic_name}</span>
            )}
            <span className="rounded bg-slate-100 px-2 py-0.5 text-sm ring-1 ring-inset ring-slate-400">
              {ROLE_LABELS[membership.role]}
            </span>
          </div>

          {clinicReady && managesPatients && <PatientTools />}

          <div className="flex items-center gap-3">
            <span>{identity.user.full_name}</span>
            <SignOutButton />
          </div>
        </div>

        <nav aria-label="Main" className="mx-auto max-w-6xl px-4">
          <ul className="flex gap-4">
            {visibleNav(membership.permissions).map((item) => (
              <li key={item.href}>
                <Link
                  href={item.href}
                  aria-current={pathname === item.href || pathname.startsWith(`/`) ? "page" : undefined}
                  className="inline-block border-b-2 border-transparent py-2 aria-[current=page]:border-blue-800 aria-[current=page]:font-semibold"
                >
                  {item.label}
                </Link>
              </li>
            ))}
          </ul>
        </nav>
      </header>

      {membership.clinic_status === "ONBOARDING" && (
        <p className="border-b border-amber-700 bg-amber-50 px-4 py-2 text-amber-950">
          Setup for this clinic is still in progress.
        </p>
      )}

      <main id="main" tabIndex={-1} className="mx-auto w-full max-w-6xl flex-1 p-4">
        {children}
      </main>
    </div>
    </RegisterPatientProvider>
  );
}

/** The header's patient tools: search and Register patient (FR-PAT-01, FR-PAT-04). */
function PatientTools() {
  const openRegister = useRegisterPatient();
  return (
    <div className="flex flex-1 items-center gap-2">
      <PatientSearch />
      {openRegister !== null && (
        <button
          type="button"
          onClick={() => openRegister()}
          className="whitespace-nowrap rounded bg-blue-800 px-3 py-2 font-semibold text-white hover:bg-blue-900"
        >
          Register patient
        </button>
      )}
    </div>
  );
}
