"use client";

import type { ReactNode } from "react";

import { Button } from "@/components/ui/Button";
import { ROLE_LABELS } from "@/features/auth/labels";
import type { Membership } from "@/features/auth/landing";
import { useSession } from "@/features/auth/SessionProvider";
import { NotificationBell } from "@/features/notifications/NotificationBell";
import { PatientSearch } from "@/features/patients/PatientSearch";
import {
  RegisterPatientProvider,
  useRegisterPatient,
} from "@/features/patients/RegisterPatientProvider";

import { useOptionalClinic } from "./ClinicGate";
import { ClinicSwitcher } from "./ClinicSwitcher";
import { visibleNav } from "./nav";
import { RolePill, Shell } from "./Shell";
import { WORKSPACE_NAV } from "./workspace";
import { useWorkspace } from "./WorkspaceProvider";
import { WorkspaceSwitch } from "./WorkspaceSwitch";

/**
 * The clinic dashboard frame (M6-P1, decision 4A) on the shared `Shell`: who and where you are,
 * the switcher for people in several clinics, the role's navigation, and sign-out. Shows the
 * person's name and role, never their phone number or email. Once the clinic has loaded, roles
 * that manage patients get the patient search (`/`) and Register patient in the header, and every
 * member gets the notification bell (M6a-P7).
 */
export function AppShell({ membership, children }: { membership: Membership; children: ReactNode }) {
  const { identity, selectClinic } = useSession();
  const clinicReady = useOptionalClinic() !== null;
  const managesPatients = membership.permissions.includes("PATIENTS_MANAGE");
  const view = useWorkspace();
  const workspace = view?.workspace ?? membership.role;

  return (
    <RegisterPatientProvider enabled={managesPatients}>
      <Shell
        navLabel="Main"
        links={visibleNav(membership.permissions, WORKSPACE_NAV[workspace])}
        person={identity.user.full_name}
        identity={
          <>
            {identity.memberships.length > 1 ? (
              <ClinicSwitcher
                memberships={identity.memberships}
                activeClinicId={membership.clinic_id}
                onSelect={selectClinic}
              />
            ) : (
              <span className="truncate font-medium">{membership.clinic_name}</span>
            )}
            <RolePill>{ROLE_LABELS[membership.role]}</RolePill>
            {view?.canSwitch === true && <WorkspaceSwitch workspace={workspace} onSwitch={view.switchTo} />}
            {/* M6a-P7: in the identity group, so it stays in the header on a phone. */}
            {clinicReady && <NotificationBell />}
          </>
        }
        {...(clinicReady && managesPatients ? { tools: <PatientTools /> } : {})}
        notice={
          membership.clinic_status === "ONBOARDING" ? (
            <p className="border-b border-amber-700 bg-amber-50 px-4 py-2 text-amber-950">
              Setup for this clinic is still in progress.
            </p>
          ) : undefined
        }
      >
        {children}
      </Shell>
    </RegisterPatientProvider>
  );
}

/** The header's patient tools: search and Register patient (FR-PAT-01, FR-PAT-04). */
function PatientTools() {
  const openRegister = useRegisterPatient();
  return (
    <>
      <PatientSearch />
      {openRegister !== null && (
        <Button variant="primary" className="whitespace-nowrap" onClick={() => openRegister()}>
          Register patient
        </Button>
      )}
    </>
  );
}
