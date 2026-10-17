"use client";

import { createContext, useCallback, useContext, useMemo, useState, type ReactNode } from "react";

import { useOptionalClinic } from "@/features/shell/ClinicGate";

import { clinicToday } from "./fields";
import { RegisterPatientDrawer, type RegisterPrefill } from "./RegisterPatientDrawer";

type OpenRegister = (prefill?: RegisterPrefill) => void;

const RegisterContext = createContext<OpenRegister | null>(null);

/** Opens the registration drawer, or null where registering is not available (no clinic loaded). */
export function useRegisterPatient(): OpenRegister | null {
  return useContext(RegisterContext);
}

/**
 * Owns the one registration drawer of the workspace, so the header button, the
 * search's "Register patient" and the results page all open the same thing. Only
 * active once the clinic has loaded: "today" for the under-18 hint is the clinic's.
 */
export function RegisterPatientProvider({ enabled, children }: { enabled: boolean; children: ReactNode }) {
  const clinic = useOptionalClinic();
  const [prefill, setPrefill] = useState<RegisterPrefill | null>(null);
  const open = useCallback<OpenRegister>((next = {}) => setPrefill(next), []);
  const value = useMemo(() => (enabled && clinic !== null ? open : null), [enabled, clinic, open]);

  return (
    <RegisterContext.Provider value={value}>
      {children}
      {value !== null && clinic !== null && prefill !== null && (
        <RegisterPatientDrawer prefill={prefill} today={clinicToday(clinic.timezone)} onClose={() => setPrefill(null)} />
      )}
    </RegisterContext.Provider>
  );
}
