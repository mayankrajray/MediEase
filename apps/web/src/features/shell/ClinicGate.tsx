"use client";

import {
  createContext,
  useContext,
  useEffect,
  useState,
  type ReactNode,
} from "react";

import { ApiError, type GetResponse } from "@/lib/api/client";
import { sessionGet } from "@/lib/auth/refresh";
import { ErrorNotice } from "@/features/auth/ErrorNotice";
import type { Membership } from "@/features/auth/landing";
import { useSession } from "@/features/auth/SessionProvider";

import { SuspendedNotice } from "./SuspendedNotice";

export type ClinicDetails = GetResponse<"/api/v1/clinic">;

export const PERM_CLINIC_REQUIRED = "PERM_CLINIC_REQUIRED";
export const CLN_SUSPENDED = "CLN_SUSPENDED";

const ClinicContext = createContext<ClinicDetails | null>(null);

/** The active clinic once it has loaded, or null (for the shell, which also shows while it loads). */
export function useOptionalClinic(): ClinicDetails | null {
  return useContext(ClinicContext);
}

/** The active clinic as the API describes it (name, status and timezone). */
export function useClinic(): ClinicDetails {
  const clinic = useContext(ClinicContext);
  if (clinic === null) {
    throw new Error("useClinic must be used inside <ClinicGate>.");
  }
  return clinic;
}

type Load =
  | { readonly status: "loading" }
  | { readonly status: "ready"; readonly clinic: ClinicDetails }
  | { readonly status: "suspended"; readonly error: unknown }
  | { readonly status: "failed"; readonly error: unknown }
  | { readonly status: "stale" };

/**
 * Loads the active clinic from `GET /api/v1/clinic` for the signed-in person
 * (with `X-Clinic-ID` when they have several), which exercises the real
 * tenancy path, surfaces a suspended clinic, and provides the clinic timezone
 * (`/me` does not carry it). Mount it with `key={clinic_id}` so switching clinic
 * starts afresh and nothing from the previous clinic is shown. `frame` wraps every state
 * (the dashboard shell), so the shell can use the clinic once it is ready while the
 * switcher keeps working when it is not.
 */
export function ClinicGate({
  membership,
  sendClinicHeader,
  frame = (body) => body,
  children,
}: {
  membership: Membership;
  sendClinicHeader: boolean;
  frame?: (body: ReactNode) => ReactNode;
  children: ReactNode;
}) {
  const session = useSession();
  const { endSession, clearClinic } = session;
  const [load, setLoad] = useState<Load>({ status: "loading" });
  const [attempt, setAttempt] = useState(0);
  const clinicId = membership.clinic_id;

  useEffect(() => {
    let cancelled = false;
    sessionGet("/api/v1/clinic", sendClinicHeader ? { clinicId } : {}).then(
      ({ data }) => {
        if (!cancelled) setLoad({ status: "ready", clinic: data });
      },
      (error: unknown) => {
        if (cancelled || endSession(error)) return;
        if (error instanceof ApiError && error.code === PERM_CLINIC_REQUIRED) {
          // The remembered clinic is no longer one of ours: forget it and ask again.
          setLoad({ status: "stale" });
          clearClinic();
        } else if (error instanceof ApiError && error.code === CLN_SUSPENDED) {
          setLoad({ status: "suspended", error });
        } else {
          setLoad({ status: "failed", error });
        }
      },
    );
    return () => {
      cancelled = true;
    };
  }, [clinicId, sendClinicHeader, attempt, endSession, clearClinic]);

  let body: ReactNode;
  switch (load.status) {
    case "ready":
      body = children;
      break;
    case "suspended":
      body = <SuspendedNotice clinicName={membership.clinic_name} error={load.error} />;
      break;
    case "failed":
      body = (
        <ErrorNotice
          error={load.error}
          onRetry={() => {
            setLoad({ status: "loading" });
            setAttempt((n) => n + 1);
          }}
        />
      );
      break;
    case "stale":
      body = null;
      break;
    case "loading":
      body = (
        <p role="status" className="text-slate-700">
          Loading {membership.clinic_name}…
        </p>
      );
      break;
  }

  return (
    <ClinicContext.Provider value={load.status === "ready" ? load.clinic : null}>
      {frame(body)}
    </ClinicContext.Provider>
  );
}