"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { TABLE, TABLE_WRAP, TD, TH, TR } from "@/components/ui/table";
import { ErrorNotice } from "@/features/auth/ErrorNotice";
import { useSession } from "@/features/auth/SessionProvider";
import type { GetResponse } from "@/lib/api/client";
import { sessionGet } from "@/lib/auth/refresh";
import { formatDateTime, formatDuration, minutesBetween } from "@/lib/format/time";

type Clinics = GetResponse<"/api/v1/ops/clinics">["items"];
type Row = Clinics[number];

type Load =
  | { readonly status: "loading" }
  | { readonly status: "ready"; readonly items: Clinics }
  | { readonly status: "failed"; readonly error: unknown };

const STATUS_LABEL: Record<Row["status"], string> = {
  ONBOARDING: "Setting up",
  ACTIVE: "Active",
  SUSPENDED: "Suspended",
};

/**
 * Every clinic with its onboarding state (FR-OPS-01, FR-OPS-04), newest first.
 * Times are shown in each clinic's own zone and labelled. The API has no
 * "owner accepted" timestamp on the checklist, so an accepted owner shows as
 * the clinic turning Active.
 */
export function ClinicList() {
  const { endSession } = useSession();
  const [load, setLoad] = useState<Load>({ status: "loading" });
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    let cancelled = false;
    sessionGet("/api/v1/ops/clinics").then(
      ({ data }) => {
        if (!cancelled) setLoad({ status: "ready", items: data.items });
      },
      (failure: unknown) => {
        if (cancelled || endSession(failure)) return;
        setLoad({ status: "failed", error: failure });
      },
    );
    return () => {
      cancelled = true;
    };
  }, [attempt, endSession]);

  return (
    <section aria-labelledby="clinics-heading" className="space-y-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h1 id="clinics-heading" className="text-2xl font-bold tracking-tight">
          Clinics
        </h1>
        <Link
          href="/ops/clinics/new"
          className="rounded-lg bg-brand-700 px-4 py-2 font-semibold text-white hover:bg-brand-800"
        >
          Create clinic
        </Link>
      </div>

      {load.status === "loading" && (
        <p role="status" className="text-slate-700">
          Loading clinics…
        </p>
      )}

      {load.status === "failed" && (
        <div className="max-w-xl">
          <ErrorNotice
            error={load.error}
            onRetry={() => {
              setLoad({ status: "loading" });
              setAttempt((n) => n + 1);
            }}
          />
        </div>
      )}

      {load.status === "ready" && load.items.length === 0 && (
        <p className="text-lg">No clinics yet. Create the first one to start onboarding.</p>
      )}

      {load.status === "ready" && load.items.length > 0 && (
        <div className={TABLE_WRAP}>
          <table role="table" className={TABLE}>
            <caption className="sr-only">Clinics, newest first</caption>
            <thead role="rowgroup">
              <tr role="row">
                <th role="columnheader" scope="col" className={TH}>Clinic</th>
                <th role="columnheader" scope="col" className={TH}>Status</th>
                <th role="columnheader" scope="col" className={TH}>Started</th>
                <th role="columnheader" scope="col" className={TH}>Steps done</th>
                <th role="columnheader" scope="col" className={TH}>Start to invitation</th>
                <th role="columnheader" scope="col" className={TH}>
                  <span className="sr-only">Actions</span>
                </th>
              </tr>
            </thead>
            <tbody role="rowgroup">
              {load.items.map((clinic) => (
                <ClinicRow key={clinic.id} clinic={clinic} />
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}

function ClinicRow({ clinic }: { clinic: Row }) {
  const checklist = clinic.onboarding;
  const toInvite =
    checklist?.staff_invited_at != null
      ? minutesBetween(checklist.started_at, checklist.staff_invited_at)
      : undefined;

  return (
    <tr role="row" className={TR}>
      <th role="rowheader" scope="row" className={`${TD} font-medium`}>
        {clinic.name}
        <span className="block font-mono text-sm font-normal text-slate-700">{clinic.slug}</span>
      </th>
      <td role="cell" data-label="Status" className={TD}>{STATUS_LABEL[clinic.status]}</td>
      <td role="cell" data-label="Started" className={TD}>
        {checklist === null ? "–" : formatDateTime(checklist.started_at, clinic.timezone)}
      </td>
      <td role="cell" data-label="Steps done" className={TD}>
        {checklist === null ? (
          "–"
        ) : (
          <>
            Clinic created: {yesNo(checklist.clinic_created_at)}
            <br />
            Doctors added: {yesNo(checklist.doctors_added_at)}
            <br />
            Staff invited: {yesNo(checklist.staff_invited_at)}
          </>
        )}
      </td>
      <td role="cell" data-label="Start to invitation" className={TD}>{toInvite === undefined ? "–" : formatDuration(toInvite)}</td>
      <td role="cell" data-label="" className={TD}>
        {clinic.status === "ONBOARDING" && (
          <Link
            href={`/ops/clinics/new?clinic=${encodeURIComponent(clinic.id)}`}
            className="text-brand-800 underline"
          >
            Continue setup{" "}
            <span className="sr-only">for {clinic.name}</span>
          </Link>
        )}
      </td>
    </tr>
  );
}

function yesNo(value: string | null): string {
  return value === null ? "no" : "yes";
}
