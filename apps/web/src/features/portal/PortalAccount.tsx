"use client";

import { useRouter } from "next/navigation";
import { useCallback, useEffect, useState } from "react";

import { Button } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { Skeleton } from "@/components/ui/Skeleton";
import { ErrorNotice } from "@/features/auth/ErrorNotice";
import type { components } from "@/lib/api/schema";
import { PORTAL_SIGN_IN_PATH, portalGet, portalPost } from "@/lib/auth/portal-session";

import { portalReasonForEndedSession } from "./messages";

type Account = components["schemas"]["PatientAccount"];

type Load =
  | { readonly status: "loading" }
  | { readonly status: "ready"; readonly account: Account }
  | { readonly status: "failed"; readonly error: unknown }
  | { readonly status: "leaving" };

const METHOD_LABELS: Record<Account["sign_in_method"], string> = {
  GOOGLE: "Google",
  PASSWORD: "Email and password",
};

/**
 * The patient's account page (M6a-P3, decision 8): who they are, how they sign in, and that no
 * clinic is linked yet. Linking and the portal dashboard come in M6b. The API re-checks the
 * portal session on every call; this only decides what to render.
 */
export function PortalAccount() {
  const router = useRouter();
  const [load, setLoad] = useState<Load>({ status: "loading" });
  const [attempt, setAttempt] = useState(0);
  const [signingOut, setSigningOut] = useState(false);

  const leave = useCallback(
    (error: unknown): boolean => {
      const reason = portalReasonForEndedSession(error);
      if (reason === undefined) return false;
      setLoad({ status: "leaving" });
      router.replace(`${PORTAL_SIGN_IN_PATH}?${new URLSearchParams({ reason }).toString()}`);
      return true;
    },
    [router],
  );

  useEffect(() => {
    let cancelled = false;
    portalGet("/api/v1/portal/me").then(
      ({ data }) => {
        if (!cancelled) setLoad({ status: "ready", account: data.account });
      },
      (error: unknown) => {
        if (cancelled || leave(error)) return;
        setLoad({ status: "failed", error });
      },
    );
    return () => {
      cancelled = true;
    };
  }, [attempt, leave]);

  async function signOut() {
    setSigningOut(true);
    try {
      await portalPost("/api/v1/portal/auth/sign-out", undefined);
    } catch {
      // The session may already be gone; leaving must still work.
    }
    router.replace(PORTAL_SIGN_IN_PATH);
  }

  if (load.status === "leaving") return null;
  if (load.status === "failed") {
    return (
      <section className="p-6 sm:p-8">
        <ErrorNotice
          error={load.error}
          onRetry={() => {
            setLoad({ status: "loading" });
            setAttempt((n) => n + 1);
          }}
        />
      </section>
    );
  }
  if (load.status === "loading") {
    return (
      <section className="space-y-3 p-6 sm:p-8" aria-busy="true">
        <p role="status" className="sr-only">
          Loading your account…
        </p>
        <Skeleton className="h-8 w-2/3" />
        <Skeleton className="h-24 w-full" />
      </section>
    );
  }

  const { account } = load;
  return (
    <section aria-labelledby="portal-account-heading" className="space-y-5 p-6 sm:p-8">
      <div>
        <h1 id="portal-account-heading" className="text-2xl font-bold tracking-tight">
          Hello, {account.full_name}
        </h1>
        <p className="mt-1 break-all text-slate-700">{account.email}</p>
      </div>

      <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-2 text-sm">
        <dt className="font-medium text-slate-900">Signs in with</dt>
        <dd className="text-slate-800">{METHOD_LABELS[account.sign_in_method]}</dd>
        <dt className="font-medium text-slate-900">Email</dt>
        <dd className="text-slate-800">{account.email_verified ? "Verified" : "Not verified yet"}</dd>
      </dl>

      <Card title="No clinic linked yet">
        <p className="text-slate-800">
          Your appointments and prescriptions will appear here once a clinic links this account to
          your record there, for example when you open a prescription link from your clinic.
        </p>
      </Card>

      <Button onClick={() => void signOut()} disabled={signingOut} className="w-full">
        {signingOut ? "Signing out…" : "Sign out"}
      </Button>
    </section>
  );
}
