"use client";

import { useCallback, useEffect, useState } from "react";

import { ApiError } from "@/lib/api/client";
import type { components } from "@/lib/api/schema";
import type { PortalStrings } from "@/lib/i18n/portal";

import { usePortal } from "./PortalShell";

type S = components["schemas"];
export type PortalLink = S["PortalLink"];
export type PortalAppointmentGroup = S["PortalAppointmentGroup"];
export type PortalAppointment = S["PortalAppointment"];
export type PortalPrescription = S["PortalPrescription"];
export type PortalReminder = S["PortalReminder"];
export type PortalBookingRequest = S["PortalBookingRequest"];

export type Loaded<T> =
  | { readonly status: "loading" }
  | { readonly status: "ready"; readonly data: T }
  | { readonly status: "failed"; readonly error: unknown };

/**
 * One screen's data through the portal session: loading, ready or failed, with an ended session
 * handed to the shell (spec R25). `load` must be stable (module-level or memoised).
 */
export function usePortalLoad<T>(load: () => Promise<T>): Loaded<T> & { readonly retry: () => void } {
  const { leave } = usePortal();
  const [state, setState] = useState<Loaded<T>>({ status: "loading" });
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    let cancelled = false;
    load().then(
      (data) => {
        if (!cancelled) setState({ status: "ready", data });
      },
      (error: unknown) => {
        if (!cancelled && !leave(error)) setState({ status: "failed", error });
      },
    );
    return () => {
      cancelled = true;
    };
  }, [load, leave, attempt]);

  const retry = useCallback(() => {
    setState({ status: "loading" });
    setAttempt((n) => n + 1);
  }, []);
  return { ...state, retry };
}

/** The portal's own words for errors it knows (spec R21); undefined means "show the API's". */
export function portalErrorText(error: unknown, s: PortalStrings): string | undefined {
  if (!(error instanceof ApiError)) return undefined;
  if (error.code === "LINK_CHALLENGE_FAILED") {
    const left = error.details["attempts_left"];
    return typeof left === "string" ? s.triesLeft(left) : s.errors.LINK_CHALLENGE_FAILED;
  }
  if (error.code === "REQ_NOT_FOUND") return s.notFound;
  const known = s.errors[error.code];
  return typeof known === "string" ? known : undefined;
}

/** The clinics' time zones by clinic ID, for reminders and prescriptions (spec R22). */
export function zonesOf(links: readonly PortalLink[]): ReadonlyMap<string, string> {
  return new Map(links.map((l) => [l.clinic.id, l.clinic.timezone]));
}

export const DEFAULT_ZONE = "Asia/Kolkata";
