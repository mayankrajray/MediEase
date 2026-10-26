"use client";

import { useState } from "react";

import { Dialog } from "@/components/Dialog";
import { Button } from "@/components/ui/Button";
import { SelectField, TextAreaField } from "@/components/ui/Field";
import { ErrorNotice } from "@/features/auth/ErrorNotice";
import { useSession } from "@/features/auth/SessionProvider";
import type { components } from "@/lib/api/schema";
import { sessionPost } from "@/lib/auth/refresh";

type SuspendReason = components["schemas"]["SuspendReason"];

const REASONS: Readonly<Record<SuspendReason, string>> = {
  VERIFICATION_PROBLEM: "A verification problem",
  CLINIC_REQUEST: "The clinic asked",
  TERMS_BREACH: "A breach of the terms",
  PAYMENT: "Payment",
  OTHER: "Other (write a note)",
};

/**
 * Suspend or reactivate a clinic (M6c-P4; FR-ONB-05; spec R56-R58), `OPS_ADMIN` only. Suspending
 * withdraws the clinic's open booking requests and tells their patients; the dialog says so.
 */
export function ClinicStatusAction({
  clinic,
  onChanged,
}: Readonly<{ clinic: { id: string; name: string; status: "ONBOARDING" | "ACTIVE" | "SUSPENDED" }; onChanged: (text: string) => void }>) {
  const { endSession } = useSession();
  const [open, setOpen] = useState(false);
  const [reason, setReason] = useState<SuspendReason | "">("");
  const [note, setNote] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const path = { pathParams: { clinic_id: clinic.id } };
  const needsNote = reason === "OTHER" && note.trim() === "";

  async function run(action: () => Promise<string>) {
    setBusy(true);
    setError(null);
    try {
      const text = await action();
      setOpen(false);
      onChanged(text);
    } catch (failure) {
      if (!endSession(failure)) setError(failure);
    } finally {
      setBusy(false);
    }
  }

  if (clinic.status === "SUSPENDED") {
    return (
      <div className="space-y-1">
        <Button
          size="sm"
          disabled={busy}
          onClick={() =>
            void run(async () => {
              await sessionPost("/api/v1/ops/clinics/{clinic_id}/reactivate", undefined, path);
              return `${clinic.name} is active again.`;
            })
          }
        >
          Reactivate <span className="sr-only">{clinic.name}</span>
        </Button>
        {error !== null && <ErrorNotice error={error} />}
      </div>
    );
  }
  if (clinic.status !== "ACTIVE") return null;

  return (
    <>
      <Button size="sm" onClick={() => setOpen(true)}>
        Suspend… <span className="sr-only">{clinic.name}</span>
      </Button>
      {open && (
        <Dialog title={`Suspend ${clinic.name}`} onClose={() => setOpen(false)}>
          <p>
            The clinic&apos;s page and booking stop at once, its staff cannot sign in to it, and every open booking request is withdrawn; each patient is told
            in the app that the clinic cannot take their request.
          </p>
          <SelectField
            id="suspend-reason"
            label="Reason (kept in the audit log)"
            required
            value={reason}
            onChange={(v) => setReason(v as SuspendReason | "")}
            options={[{ value: "", label: "Choose a reason" }, ...(Object.keys(REASONS) as SuspendReason[]).map((r) => ({ value: r, label: REASONS[r] }))]}
          />
          <TextAreaField
            id="suspend-note"
            label="Note for MediEase"
            value={note}
            onChange={setNote}
            maxLength={500}
            hint="Not shown to the clinic or its patients. Required for Other."
            {...(needsNote ? { error: "Write a note for Other." } : {})}
          />
          {error !== null && <ErrorNotice error={error} />}
          <div className="flex flex-wrap justify-end gap-2">
            <Button onClick={() => setOpen(false)}>Go back</Button>
            <Button
              variant="danger"
              disabled={busy || reason === "" || needsNote}
              onClick={() =>
                void run(async () => {
                  if (reason === "") return "";
                  const { data } = await sessionPost("/api/v1/ops/clinics/{clinic_id}/suspend", { reason, note: note.trim() === "" ? null : note }, path);
                  const n = data.requests_withdrawn;
                  return `${clinic.name} is suspended. ${n === 1 ? "1 open request was" : `${n} open requests were`} withdrawn.`;
                })
              }
            >
              Suspend the clinic
            </Button>
          </div>
        </Dialog>
      )}
    </>
  );
}
