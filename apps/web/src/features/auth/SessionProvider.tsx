"use client";

import { useRouter } from "next/navigation";
import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from "react";

import { apiPost } from "@/lib/api/client";
import { readCsrfToken } from "@/lib/api/csrf";
import { sessionGet } from "@/lib/auth/refresh";

import { forgetClinic, readRememberedClinic, rememberClinic } from "./clinic-selection";
import { chooseClinic, type ClinicChoice, type Identity } from "./landing";
import { ErrorNotice } from "./ErrorNotice";
import { reasonForEndedSession, type SignInReason } from "./messages";

export interface SessionValue {
  readonly identity: Identity;
  /** The clinic this tab works in (or that a choice is still needed). */
  readonly clinic: ClinicChoice;
  /** Work in another of the person's clinics; ignored if it is not one of them. */
  readonly selectClinic: (clinicId: string) => void;
  /** Ends the session on the server and leaves for the sign-in page. Always completes locally. */
  readonly signOut: () => Promise<void>;
  /**
   * For callers whose request failed: if the error means the session is over,
   * leaves for the sign-in page (with the reason) and returns true.
   */
  readonly endSession: (error: unknown) => boolean;
}

const SessionContext = createContext<SessionValue | null>(null);

export function useSession(): SessionValue {
  const value = useContext(SessionContext);
  if (value === null) {
    throw new Error("useSession must be used inside <SessionProvider>.");
  }
  return value;
}

type Load =
  | { readonly status: "loading" }
  | { readonly status: "ready"; readonly identity: Identity }
  | { readonly status: "failed"; readonly error: unknown }
  | { readonly status: "leaving" };

/**
 * The browser's view of who is signed in (M1-P6 design, concepts 1-3).
 *
 * The session tokens are HttpOnly and `me_access` is not even sent on page
 * navigations (cookie path `/api`), so the only way to know is to ask the API:
 * `GET /api/v1/me`, which refreshes an expired access token once. This is a
 * convenience for the UI, not a security boundary: the API re-checks everything
 * on every request.
 */
export function SessionProvider({ children }: { children: ReactNode }) {
  const router = useRouter();
  const [load, setLoad] = useState<Load>({ status: "loading" });
  const [chosen, setChosen] = useState<string | null>(null);
  const [attempt, setAttempt] = useState(0);

  const leave = useCallback(
    (reason: SignInReason | undefined) => {
      const query = new URLSearchParams({
        next: `${window.location.pathname}${window.location.search}`,
      });
      if (reason !== undefined) {
        query.set("reason", reason);
      }
      router.replace(`/sign-in?${query.toString()}`);
    },
    [router],
  );

  useEffect(() => {
    let cancelled = false;
    // Without a CSRF cookie this visitor was never signed in: do not claim a session "ended".
    const hadSession = readCsrfToken() !== undefined;

    sessionGet("/api/v1/me").then(
      ({ data }) => {
        if (cancelled) return;
        setChosen(readRememberedClinic());
        setLoad({ status: "ready", identity: data });
      },
      (error: unknown) => {
        if (cancelled) return;
        const reason = reasonForEndedSession(error);
        if (reason === undefined) {
          setLoad({ status: "failed", error });
          return;
        }
        setLoad({ status: "leaving" });
        leave(reason === "session_ended" && !hadSession ? undefined : reason);
      },
    );

    return () => {
      cancelled = true;
    };
  }, [attempt, leave]);

  const reload = useCallback(() => {
    setLoad({ status: "loading" });
    setAttempt((n) => n + 1);
  }, []);

  const identity = load.status === "ready" ? load.identity : undefined;

  const value = useMemo<SessionValue | null>(() => {
    if (identity === undefined) {
      return null;
    }
    return {
      identity,
      clinic: chooseClinic(identity.memberships, chosen),
      selectClinic: (clinicId) => {
        if (identity.memberships.some((m) => m.clinic_id === clinicId)) {
          setChosen(clinicId);
          rememberClinic(clinicId);
        }
      },
      signOut: async () => {
        try {
          await apiPost("/api/v1/auth/sign-out", undefined);
        } catch {
          // The server may be unreachable or the session already gone; leaving must still work.
        }
        forgetClinic();
        router.replace("/sign-in");
      },
      endSession: (error) => {
        const reason = reasonForEndedSession(error);
        if (reason === undefined) {
          return false;
        }
        forgetClinic();
        leave(reason);
        return true;
      },
    };
  }, [identity, chosen, router, leave]);

  if (value !== null) {
    return <SessionContext.Provider value={value}>{children}</SessionContext.Provider>;
  }
  if (load.status === "failed") {
    return (
      <main className="mx-auto max-w-xl p-6">
        <ErrorNotice error={load.error} onRetry={reload} />
      </main>
    );
  }
  if (load.status === "leaving") {
    return null;
  }
  return (
    <main className="mx-auto max-w-xl p-6">
      <p role="status" className="text-slate-700">
        Loading your session…
      </p>
    </main>
  );
}
