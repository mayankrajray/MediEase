"use client";

import { useState } from "react";

import { Button } from "@/components/ui/Button";
import { SelectField } from "@/components/ui/Field";
import { ErrorNotice } from "@/features/auth/ErrorNotice";
import { useSession } from "@/features/auth/SessionProvider";
import { PLANS, PLAN_LABELS, setPlan, trialText, type Plan, type PlanSummary } from "@/features/plan/api";

/**
 * The clinic's plan and trial on the ops list, and the plan picker (M6d-P7; plans R7, R8),
 * `OPS_ADMIN` only. A plan smaller than what the clinic uses is refused by the API, which says
 * which limit (SUB_PLAN_TOO_SMALL).
 */
export function ClinicPlanAction({
  clinic,
  onChanged,
}: Readonly<{ clinic: { id: string; name: string; subscription: PlanSummary }; onChanged: (text: string) => void }>) {
  const { endSession } = useSession();
  const [plan, setChoice] = useState<Plan>(clinic.subscription.plan);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const trial = trialText(clinic.subscription);

  async function save() {
    setBusy(true);
    setError(null);
    try {
      await setPlan(clinic.id, plan);
      onChanged(`${clinic.name} is now on the ${PLAN_LABELS[plan]} plan.`);
    } catch (failure) {
      if (!endSession(failure)) setError(failure);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-1">
      {trial !== undefined && (
        <span className={`block text-sm ${clinic.subscription.trial_state === "ENDED" ? "font-semibold text-amber-900" : "text-slate-700"}`}>{trial}</span>
      )}
      <div className="flex flex-wrap items-end gap-2">
        <SelectField
          id={`plan-${clinic.id}`}
          label={`Plan for ${clinic.name}`}
          value={plan}
          onChange={(v) => setChoice(v as Plan)}
          options={PLANS.map((p) => ({ value: p, label: PLAN_LABELS[p] }))}
        />
        <Button size="sm" disabled={busy || plan === clinic.subscription.plan} onClick={() => void save()}>
          Save plan <span className="sr-only">for {clinic.name}</span>
        </Button>
      </div>
      {error !== null && <ErrorNotice error={error} />}
    </div>
  );
}
