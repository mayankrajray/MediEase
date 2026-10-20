"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState, type ReactNode } from "react";

import { Drawer } from "@/components/Drawer";
import { Button } from "@/components/ui/Button";
import { cx } from "@/components/ui/cx";
import { MotionProvider } from "@/components/ui/Motion";
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
import { visibleNav, type Permission } from "./nav";
import { SignOutButton } from "./SignOutButton";

/**
 * The clinic dashboard frame (M6-P1, decision 4A): who and where you are, the switcher for people
 * in several clinics, navigation, and sign-out. Responsive from 360 px: from 1024 px the
 * navigation is a left sidebar; below that a Menu button opens it in a drawer (a native
 * `<dialog>`: focus stays inside, Escape closes). Built for keyboard use too (apps/web/CLAUDE.md).
 * Shows the person's name and role, never their phone number or email. Once the clinic has
 * loaded, roles that manage patients get the patient search (`/`) and Register patient in the
 * header. Motion is available to every screen inside (decision 3A).
 */
export function AppShell({ membership, children }: { membership: Membership; children: ReactNode }) {
  const { identity, selectClinic } = useSession();
  const clinicReady = useOptionalClinic() !== null;
  const managesPatients = membership.permissions.includes("PATIENTS_MANAGE");
  const [menuOpen, setMenuOpen] = useState(false);

  return (
    <RegisterPatientProvider enabled={managesPatients}>
      <MotionProvider>
        <div className="min-h-screen bg-canvas lg:flex">
          <a
            href="#main"
            className="sr-only focus:not-sr-only focus:absolute focus:left-2 focus:top-2 focus:z-30 focus:rounded focus:bg-white focus:p-2"
          >
            Skip to content
          </a>

          <aside className="hidden border-r border-slate-200 bg-white lg:flex lg:w-60 lg:shrink-0 lg:flex-col">
            <div className="px-5 py-4">
              <Brand />
            </div>
            <NavLinks permissions={membership.permissions} />
          </aside>

          <div className="flex min-w-0 flex-1 flex-col">
            <header className="sticky top-0 z-20 border-b border-slate-200 bg-white">
              <div className="flex flex-wrap items-center justify-between gap-x-4 gap-y-2 px-4 py-3">
                <div className="order-1 flex min-w-0 flex-wrap items-center gap-x-3 gap-y-2">
                  <Button
                    variant="secondary"
                    size="sm"
                    className="lg:hidden"
                    aria-haspopup="dialog"
                    aria-expanded={menuOpen}
                    onClick={() => setMenuOpen(true)}
                  >
                    Menu
                  </Button>
                  <span className="lg:hidden">
                    <Brand compact />
                  </span>
                  {identity.memberships.length > 1 ? (
                    <ClinicSwitcher
                      memberships={identity.memberships}
                      activeClinicId={membership.clinic_id}
                      onSelect={selectClinic}
                    />
                  ) : (
                    <span className="truncate font-medium">{membership.clinic_name}</span>
                  )}
                  <span className="rounded-full bg-brand-50 px-2.5 py-0.5 text-sm font-medium text-brand-900 ring-1 ring-inset ring-brand-200">
                    {ROLE_LABELS[membership.role]}
                  </span>
                </div>

                <div className="order-2 hidden items-center gap-3 sm:flex lg:order-3">
                  <span className="hidden sm:inline">{identity.user.full_name}</span>
                  <SignOutButton />
                </div>

                {clinicReady && managesPatients && <PatientTools />}
              </div>
            </header>

            {membership.clinic_status === "ONBOARDING" && (
              <p className="border-b border-amber-700 bg-amber-50 px-4 py-2 text-amber-950">
                Setup for this clinic is still in progress.
              </p>
            )}

            <main id="main" tabIndex={-1} className="mx-auto w-full max-w-6xl flex-1 p-4 sm:p-6">
              {children}
            </main>
          </div>
        </div>

        {menuOpen && (
          <Drawer title="Menu" side="left" onClose={() => setMenuOpen(false)}>
            <p className="text-sm text-slate-700">
              {identity.user.full_name} · {ROLE_LABELS[membership.role]}
            </p>
            <NavLinks permissions={membership.permissions} onNavigate={() => setMenuOpen(false)} />
            {/* On a phone the header has no room for it: Sign out lives here too. */}
            <div className="sm:hidden">
              <SignOutButton />
            </div>
          </Drawer>
        )}
      </MotionProvider>
    </RegisterPatientProvider>
  );
}

function Brand({ compact = false }: { compact?: boolean }) {
  return (
    <span className="flex items-center gap-2 text-lg font-bold text-slate-900">
      <span aria-hidden="true" className="grid size-7 place-items-center rounded-lg bg-brand-700 text-sm text-white">
        M
      </span>
      {/* On a phone the mark alone, so the clinic and role fit on one line. */}
      <span className={compact ? "sr-only sm:not-sr-only" : undefined}>MediEase</span>
    </span>
  );
}

/** The role's sections, with the one being shown marked as current (a link, not a colour only). */
function NavLinks({ permissions, onNavigate }: { permissions: readonly Permission[]; onNavigate?: () => void }) {
  const pathname = usePathname();
  return (
    <nav aria-label="Main" className="px-3 pb-4">
      <ul className="space-y-1">
        {visibleNav(permissions).map((item) => {
          const current = pathname === item.href || pathname.startsWith(`${item.href}/`);
          return (
            <li key={item.href}>
              <Link
                href={item.href}
                {...(onNavigate === undefined ? {} : { onClick: onNavigate })}
                aria-current={current ? "page" : undefined}
                className={cx(
                  "flex min-h-10 items-center rounded-lg px-3 py-2 font-medium transition-colors motion-reduce:transition-none",
                  current ? "bg-brand-50 text-brand-900 ring-1 ring-inset ring-brand-200" : "text-slate-700 hover:bg-slate-100",
                )}
              >
                {item.label}
              </Link>
            </li>
          );
        })}
      </ul>
    </nav>
  );
}

/** The header's patient tools: search and Register patient (FR-PAT-01, FR-PAT-04). */
function PatientTools() {
  const openRegister = useRegisterPatient();
  return (
    <div className="order-3 flex w-full items-center gap-2 lg:order-2 lg:w-auto lg:flex-1">
      <PatientSearch />
      {openRegister !== null && (
        <Button variant="primary" className="whitespace-nowrap" onClick={() => openRegister()}>
          Register patient
        </Button>
      )}
    </div>
  );
}
