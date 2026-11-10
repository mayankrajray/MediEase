"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useRef, useState } from "react";

import { ArrowLeft, CircleCheck, FileSearch, Pill } from "lucide-react";

import { Dialog } from "@/components/Dialog";
import { Alert } from "@/components/ui/Alert";
import { Avatar } from "@/components/ui/Avatar";
import { Button, buttonClasses } from "@/components/ui/Button";
import { EmptyState } from "@/components/ui/EmptyState";
import { Skeleton } from "@/components/ui/Skeleton";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { ErrorNotice } from "@/features/auth/ErrorNotice";
import { useSession } from "@/features/auth/SessionProvider";
import { useAppointmentApi, type Doctor } from "@/features/appointments/api";
import { AttachmentsPanel } from "@/features/attachments/AttachmentsPanel";
import { ageText, clinicToday, isNotFound, LANGUAGE_LABELS, SEX_LABELS } from "@/features/patients/fields";
import { patientPath } from "@/features/patients/RegisterPatientDrawer";
import { useRxApi, type Consultation } from "@/features/prescriptions/api";
import { toLine } from "@/features/prescriptions/draft";
import { IssuedActions } from "@/features/prescriptions/IssuedActions";
import { RxBuilder, type BuilderHandle } from "@/features/prescriptions/RxBuilder";
import { useClinic } from "@/features/shell/ClinicGate";

import { Addenda } from "./Addenda";
import { HistoryTimeline } from "./HistoryTimeline";
import { CARD_TITLE } from "./card";
import { VisitNotes } from "./VisitNotes";

type Load =
  | { readonly status: "loading" }
  | { readonly status: "ready"; readonly consultation: Consultation; readonly doctors: readonly Doctor[]; readonly loaded: number }
  | { readonly status: "failed"; readonly error: unknown };

/**
 * The consultation screen (spec §6, M4-P6 journey steps 2-5), one page at 1366 × 768: the
 * patient and their earlier visits on the left; notes, vitals and the prescription on the
 * right. Only the visit's own doctor writes (CLINICAL_WRITE and the visit's doctor profile);
 * others with CLINICAL_VIEW read. Each load is one audited read on the API (R16).
 */
export function ConsultationScreen({ visitId }: Readonly<{ visitId: string }>) {
  const clinic = useClinic();
  const router = useRouter();
  const api = useRxApi();
  const appointments = useAppointmentApi();
  const { identity, clinic: choice, endSession } = useSession();
  const canWrite = choice.kind === "active" && choice.membership.permissions.includes("CLINICAL_WRITE");
  const [load, setLoad] = useState<Load>({ status: "loading" });
  const [generation, setGeneration] = useState(0);
  const [confirming, setConfirming] = useState(false);
  const [completing, setCompleting] = useState(false);
  const [completeError, setCompleteError] = useState<unknown>(undefined);
  const builder = useRef<BuilderHandle | null>(null);
  const flushers = useRef(new Set<() => Promise<boolean>>());

  useEffect(() => {
    let cancelled = false;
    Promise.all([api.consultation(visitId), canWrite ? appointments.doctors() : Promise.resolve([] as readonly Doctor[])]).then(
      ([consultation, doctors]) => {
        // The editors are keyed on this load, so they start again from the data just fetched.
        if (!cancelled) setLoad({ status: "ready", consultation, doctors, loaded: generation });
      },
      (error: unknown) => {
        if (!cancelled && !endSession(error)) setLoad({ status: "failed", error });
      },
    );
    return () => {
      cancelled = true;
    };
  }, [api, appointments, visitId, generation, canWrite, endSession]);

  const register = useCallback((flush: () => Promise<boolean>) => {
    flushers.current.add(flush);
    return () => {
      flushers.current.delete(flush);
    };
  }, []);

  const saveAll = useCallback(async () => {
    const results = await Promise.all([...flushers.current].map((flush) => flush()));
    return results.every(Boolean);
  }, []);

  const reload = useCallback(() => {
    void saveAll().finally(() => setGeneration((n) => n + 1));
  }, [saveAll]);

  if (load.status === "loading") {
    return (
      <div className="space-y-4" aria-busy="true">
        <p role="status" className="sr-only">
          Loading the consultation…
        </p>
        <Skeleton className="h-20 w-full" />
        <div className="grid gap-6 lg:grid-cols-[20rem_minmax(0,1fr)]">
          <Skeleton className="h-40 w-full" />
          <Skeleton className="h-80 w-full" />
        </div>
      </div>
    );
  }
  if (load.status === "failed") {
    return isNotFound(load.error) ? (
      <EmptyState
        title="Visit not found"
        icon={<FileSearch className="size-5" />}
        action={
          <Link href="/queue" className={buttonClasses("secondary", "md")}>
            <ArrowLeft aria-hidden="true" className="size-4" />
            Back to the queue
          </Link>
        }
      >
        <h1 className="sr-only">Visit not found</h1>
        This visit is not in {clinic.name}.
      </EmptyState>
    ) : (
      <ErrorNotice error={load.error} onRetry={() => setGeneration((n) => n + 1)} />
    );
  }

  const { consultation, doctors, loaded } = load;
  const { visit, patient, history, prescriptions } = consultation;
  const writer = canWrite && doctors.some((d) => d.id === visit.doctor_id && d.user_id === identity.user.id);
  const locked = visit.is_locked;
  const latest = prescriptions.at(-1);
  const draft = latest?.status === "DRAFT" ? latest : undefined;
  const issued = latest?.status === "ISSUED" ? latest : undefined;
  // Version 1 is written until the lock (P2 2A); a revision may correct an issued one at any time.
  const rxEditable = writer && (draft !== undefined ? draft.version > 1 || !locked : issued === undefined && !locked);
  const today = clinicToday(clinic.timezone);

  async function complete(confirmed: boolean) {
    setCompleteError(undefined);
    if (!confirmed && builder.current?.hasContent() === true) {
      setConfirming(true);
      return;
    }
    setConfirming(false);
    setCompleting(true);
    if (!(await saveAll())) {
      setCompleting(false);
      return;
    }
    api.completeVisit(visit.id).then(
      () => router.push("/queue"),
      (failure: unknown) => {
        setCompleting(false);
        if (!endSession(failure)) setCompleteError(failure);
      },
    );
  }

  return (
    <article aria-labelledby="consultation-heading" className="space-y-4">
      <header className="flex flex-wrap items-center justify-between gap-4 rounded-card border border-line bg-white p-4 shadow-card">
        <div className="flex min-w-0 items-center gap-3">
          <Avatar name={patient.full_name} size="lg" />
          <div className="min-w-0">
            <p className="text-xs font-semibold uppercase tracking-wide text-slate-600">Consultation</p>
            <h1 id="consultation-heading" className="text-xl font-bold tracking-tight sm:text-2xl">
              <Link href={patientPath(patient.id)} className="text-slate-900 underline-offset-4 hover:text-brand-800 hover:underline [overflow-wrap:anywhere]">
                {patient.full_name}
              </Link>
            </h1>
            <p className="text-sm text-slate-700">
              {`${patient.code} · ${ageText(patient)} · ${SEX_LABELS[patient.sex]} · reads ${LANGUAGE_LABELS[patient.language]}`}
              {patient.is_minor && " · under 18"}
            </p>
          </div>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <StatusBadge tone={visit.status === "OPEN" ? "active" : locked ? "neutral" : "done"}>
            {visit.status === "OPEN" ? "In consultation" : locked ? "Completed · locked" : "Completed · notes editable for 24 hours"}
          </StatusBadge>
          <Link href="/queue" className={buttonClasses("secondary", "md")}>
            <ArrowLeft aria-hidden="true" className="size-4" />
            Back to the queue
          </Link>
          {writer && visit.status === "OPEN" && (
            <Button variant="primary" loading={completing} onClick={() => void complete(false)} icon={<CircleCheck className="size-4" />}>
              {completing ? "Completing…" : "Complete visit"}
            </Button>
          )}
        </div>
      </header>
      {completeError !== undefined && <ErrorNotice error={completeError} />}
      {!writer && <Alert tone="info">{canWrite ? "This is another doctor's visit: you can read it but not change it." : "Read only."}</Alert>}

      <div className="grid gap-6 lg:grid-cols-[20rem_minmax(0,1fr)]">
        <aside className="space-y-4">
          <HistoryTimeline
            history={history}
            timeZone={clinic.timezone}
            onRepeat={rxEditable ? (v) => builder.current?.add((v.prescription?.items ?? []).map((item) => toLine(item))) : undefined}
          />
        </aside>
        <div className="space-y-6">
          <VisitNotes key={`notes-${loaded}`} visit={visit} editable={writer && !locked} register={register} onReload={reload} />
          {rxEditable ? (
            <RxBuilder
              key={`rx-${loaded}`}
              visitId={visit.id}
              draft={draft}
              today={today}
              language={patient.language}
              handle={builder}
              register={register}
              onIssued={reload}
              onReload={reload}
            />
          ) : issued !== undefined ? (
            <IssuedActions rx={issued} canRevise={writer} onRevised={reload} chainId={(prescriptions.find((p) => p.version === 1) ?? issued).id} />
          ) : (
            <section aria-labelledby="rx-heading" className="space-y-3 rounded-card border border-line bg-white p-4 shadow-card">
              <h2 id="rx-heading" className={CARD_TITLE}>
                <Pill aria-hidden="true" className="size-5 text-brand-700" />
                Prescription
              </h2>
              <p className="text-slate-700">{draft !== undefined ? "Being written by the doctor; not issued yet." : "No prescription for this visit."}</p>
            </section>
          )}
          <Addenda visit={visit} canAdd={writer && locked} timeZone={clinic.timezone} onAdded={reload} />
          <AttachmentsPanel visitId={visit.id} canShare={writer} timeZone={clinic.timezone} />
        </div>
      </div>

      {confirming && (
        <Dialog title="Complete without issuing?" onClose={() => setConfirming(false)}>
          <p>The prescription is written but not issued, so the patient gets nothing to print or open. You can still issue it afterwards.</p>
          <div className="flex flex-wrap justify-end gap-2">
            <Button data-autofocus onClick={() => setConfirming(false)}>
              Go back
            </Button>
            <Button variant="primary" onClick={() => void complete(true)}>
              Complete anyway
            </Button>
          </div>
        </Dialog>
      )}
    </article>
  );
}
