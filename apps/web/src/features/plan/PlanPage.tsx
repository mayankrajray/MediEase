"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { PageHeader } from "@/components/ui/PageHeader";
import { ErrorNotice } from "@/features/auth/ErrorNotice";
import { useSession } from "@/features/auth/SessionProvider";
import { useClinic } from "@/features/shell/ClinicGate";
import { formatDateTime } from "@/lib/format/time";

import { trialText, useSubscriptionApi, type Subscription } from "./api";

function used(n: number, of: number | null): string {
  return of === null ? `${n} (no limit)` : `${n} of ${of}`;
}

/**
 * *Plan* (M6d-P7; FR-SUB-01; plans R6): the owner's plan, what the clinic uses of it and the
 * trial. MediEase changes the plan (R8); nothing here does.
 */
export function PlanPage() {
  const api = useSubscriptionApi();
  const clinic = useClinic();
  const { endSession } = useSession();
  const [subscription, setSubscription] = useState<Subscription | undefined>(undefined);
  const [error, setError] = useState<unknown>(null);

  useEffect(() => {
    let cancelled = false;
    api.get().then(
      (s) => {
        if (!cancelled) setSubscription(s);
      },
      (failure: unknown) => {
        if (!cancelled && !endSession(failure)) setError(failure);
      },
    );
    return () => {
      cancelled = true;
    };
  }, [api, endSession]);

  const trial = subscription === undefined ? undefined : trialText(subscription);
  return (
    <section className="space-y-4">
      <PageHeader title="Plan" description={subscription?.plan_name} />
      {error !== null && <ErrorNotice error={error} />}
      {subscription === undefined && error === null && <p role="status">Loading the plan…</p>}
      {subscription !== undefined && (
        <div className="space-y-4 rounded-card border border-slate-200 bg-white p-4 shadow-card">
          <dl className="grid gap-3 sm:grid-cols-2">
            <div>
              <dt className="text-sm font-medium text-slate-700">Doctors</dt>
              <dd className="text-lg font-semibold">{used(subscription.usage.doctors, subscription.limits.doctors)}</dd>
            </div>
            <div>
              <dt className="text-sm font-medium text-slate-700">People in the team (you included)</dt>
              <dd className="text-lg font-semibold">{used(subscription.usage.users, subscription.limits.users)}</dd>
            </div>
          </dl>
          {trial !== undefined && (
            <p className={subscription.trial_state === "ENDED" ? "font-medium text-amber-900" : "text-slate-800"}>
              {trial}
              {subscription.trial_ends_at !== null &&
                ` (${subscription.trial_state === "ENDED" ? "ended" : "ends"} ${formatDateTime(subscription.trial_ends_at, clinic.timezone)})`}
            </p>
          )}
          <p className="text-slate-700">Invited people count until they join or are removed. To change the plan of {clinic.name}, contact MediEase.</p>
        </div>
      )}
    </section>
  );
}

/** M6d-P7 (D5): an ended trial is said to owners on every page; nothing is locked. */
export function TrialNotice() {
  const api = useSubscriptionApi();
  const [ended, setEnded] = useState(false);
  useEffect(() => {
    let cancelled = false;
    api.get().then(
      (s) => {
        if (!cancelled) setEnded(s.trial_state === "ENDED");
      },
      () => undefined,
    );
    return () => {
      cancelled = true;
    };
  }, [api]);
  if (!ended) return null;
  return (
    <p role="status" className="border-b border-amber-700 bg-amber-50 px-4 py-2 text-amber-950">
      Your free trial has ended. Everything keeps working; contact MediEase to choose your plan.{" "}
      <Link href="/settings/plan" className="font-medium underline">
        See your plan
      </Link>
    </p>
  );
}
