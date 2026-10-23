"use client";

import Link from "next/link";
import { useCallback, useEffect, useId, useState, type FormEvent } from "react";

import { Button } from "@/components/ui/Button";
import { EmptyState } from "@/components/ui/EmptyState";
import { INPUT, LABEL } from "@/components/ui/Field";
import { PageHeader } from "@/components/ui/PageHeader";
import { Skeleton } from "@/components/ui/Skeleton";
import { TABLE, TABLE_WRAP, TD, TH, TR } from "@/components/ui/table";
import { ErrorNotice } from "@/features/auth/ErrorNotice";
import { useSession } from "@/features/auth/SessionProvider";
import { useClinic } from "@/features/shell/ClinicGate";
import type { components } from "@/lib/api/schema";
import { sessionGet } from "@/lib/auth/refresh";
import { formatDateTime } from "@/lib/format/time";

import { SEX_LABELS, ageText } from "./fields";
import { patientPath } from "./RegisterPatientDrawer";

export type MyPatient = components["schemas"]["MyPatient"];
export const MY_PATIENTS_PAGE = 50;

type Load =
  | { readonly status: "loading" }
  | { readonly status: "ready"; readonly items: readonly MyPatient[]; readonly more: boolean }
  | { readonly status: "failed"; readonly error: unknown };

/**
 * *My Patients* (M6a-P6, decision 5A; FR-UX-02, FR-UX-06): the patients I have seen as a doctor
 * here, latest visit first, 50 at a time, narrowed by name, code or phone like the lookup box.
 * Who and when only; each row opens the patient's profile. For doctors and practising owners:
 * anyone else is told so by the API.
 */
export function MyPatients() {
  const clinic = useClinic();
  const { clinic: choice, endSession } = useSession();
  const clinicId = choice.kind === "active" && choice.sendClinicHeader ? choice.membership.clinic_id : undefined;
  const [text, setText] = useState("");
  const [q, setQ] = useState("");
  const [attempt, setAttempt] = useState(0);
  const [load, setLoad] = useState<Load>({ status: "loading" });
  const [loadingMore, setLoadingMore] = useState(false);
  const searchId = useId();

  const page = useCallback(
    (offset: number) =>
      sessionGet("/api/v1/my-patients", {
        ...(clinicId === undefined ? {} : { clinicId }),
        query: { q: q === "" ? undefined : q, limit: String(MY_PATIENTS_PAGE), offset: String(offset) },
      }).then(({ data }) => data.items),
    [clinicId, q],
  );

  useEffect(() => {
    let cancelled = false;
    page(0).then(
      (items) => {
        if (!cancelled) setLoad({ status: "ready", items, more: items.length === MY_PATIENTS_PAGE });
      },
      (failure: unknown) => {
        if (!cancelled && !endSession(failure)) setLoad({ status: "failed", error: failure });
      },
    );
    return () => {
      cancelled = true;
    };
  }, [page, attempt, endSession]);

  function search(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const next = text.trim();
    if (next === q) return;
    setLoad({ status: "loading" });
    setQ(next);
  }

  async function showMore(current: readonly MyPatient[]) {
    setLoadingMore(true);
    try {
      const next = await page(current.length);
      setLoad({ status: "ready", items: [...current, ...next], more: next.length === MY_PATIENTS_PAGE });
    } catch (failure) {
      if (!endSession(failure)) setLoad({ status: "failed", error: failure });
    } finally {
      setLoadingMore(false);
    }
  }

  return (
    <section className="space-y-4">
      <PageHeader title="My patients" description="Patients you have seen in this clinic, latest visit first." />
      <form role="search" onSubmit={search} className="flex max-w-xl flex-wrap items-end gap-2">
        <div className="min-w-0 flex-1">
          <label htmlFor={searchId} className={LABEL}>
            Find one of my patients
          </label>
          <input
            id={searchId}
            type="search"
            value={text}
            maxLength={100}
            onChange={(event) => setText(event.target.value)}
            placeholder="Name, code or phone"
            className={INPUT}
          />
        </div>
        <Button type="submit">Search</Button>
      </form>

      {load.status === "loading" && (
        <div className="space-y-2">
          <p role="status" className="sr-only">
            Loading your patients…
          </p>
          <Skeleton className="h-12 w-full" />
          <Skeleton className="h-12 w-full" />
        </div>
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
        <EmptyState title={q === "" ? "You have not seen any patients here yet." : "None of your patients match."}>
          {q === "" ? "A patient appears here once you start their consultation." : "Try another name, code or phone."}
        </EmptyState>
      )}
      {load.status === "ready" && load.items.length > 0 && (
        <div className={TABLE_WRAP}>
          <table role="table" className={TABLE}>
            <caption className="sr-only">My patients, latest visit first</caption>
            <thead role="rowgroup">
              <tr role="row">
                <th role="columnheader" scope="col" className={TH}>Patient</th>
                <th role="columnheader" scope="col" className={TH}>Age and sex</th>
                <th role="columnheader" scope="col" className={TH}>Last visit</th>
                <th role="columnheader" scope="col" className={TH}>Visits</th>
              </tr>
            </thead>
            <tbody role="rowgroup">
              {load.items.map((p) => (
                <tr role="row" key={p.id} className={TR}>
                  <th role="rowheader" scope="row" className={`${TD} font-medium`}>
                    <Link href={patientPath(p.id)} className="text-brand-800 underline-offset-2 hover:underline">
                      {p.full_name}
                    </Link>
                    <span className="block font-mono text-sm font-normal text-slate-700">{p.code}</span>
                  </th>
                  <td role="cell" data-label="Age and sex" className={TD}>
                    {ageText(p)} · {SEX_LABELS[p.sex]}
                  </td>
                  <td role="cell" data-label="Last visit" className={TD}>
                    {formatDateTime(p.last_visit_at, clinic.timezone)}
                  </td>
                  <td role="cell" data-label="Visits" className={`${TD} tabular-nums`}>
                    {p.visits}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      {load.status === "ready" && load.more && (
        <Button disabled={loadingMore} onClick={() => void showMore(load.items)}>
          {loadingMore ? "Loading…" : "Show more"}
        </Button>
      )}
    </section>
  );
}
