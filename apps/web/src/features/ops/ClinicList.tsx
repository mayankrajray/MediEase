"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

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
        <h1 id="clinics-heading" className="text-2xl font-bold">
          Clinics
        </h1>
        <Link
          href="/ops/clinics/new"
          className="rounded bg-blue-800 px-4 py-2 font-semibold text-white hover:bg-blue-900"
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
        <div className="overflow-x-auto">
          <table className="w-full border-collapse text-left">
            <caption className="sr-only">Clinics, newest first</caption>
            <thead>
              <tr className="border-b border-slate-400">
                <th scope="col" className="py-2 pr-4">Clinic</th>
                <th scope="col" className="py-2 pr-4">Status</th>
                <th scope="col" className="py-2 pr-4">Started</th>
                <th scope="col" className="py-2 pr-4">Steps done</th>
                <th scope="col" className="py-2 pr-4">Start to invitation</th>
                <th scope="col" className="py-2">
                  <span className="sr-only">Actions</span>
                </th>
              </tr>
            </thead>
            <tbody>
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
    <tr className="border-b border-slate-200 align-top">
      <th scope="row" className="py-2 pr-4 font-medium">
        {clinic.name}
        <span className="block font-mono text-sm font-normal text-slate-700">{clinic.slug}</span>
      </th>
      <td className="py-2 pr-4">{STATUS_LABEL[clinic.status]}</td>
      <td className="py-2 pr-4">
        {checklist === null ? "–" : formatDateTime(checklist.started_at, clinic.timezone)}
      </td>
      <td className="py-2 pr-4">
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
      <td className="py-2 pr-4">{toInvite === undefined ? "–" : formatDuration(toInvite)}</td>
      <td className="py-2">
        {clinic.status === "ONBOARDING" && (
          <Link
            href={`/ops/clinics/new?clinic=${encodeURIComponent(clinic.id)}`}
            className="text-blue-800 underline"
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
