"use client";

import { Search, SearchX, UserPlus } from "lucide-react";
import Link from "next/link";
import { useEffect, useState } from "react";

import { Avatar } from "@/components/ui/Avatar";
import { Button } from "@/components/ui/Button";
import { EmptyState } from "@/components/ui/EmptyState";
import { ListSkeleton } from "@/components/ui/Skeleton";
import { TABLE, TABLE_WRAP, TD, TH, TR } from "@/components/ui/table";
import { ErrorNotice } from "@/features/auth/ErrorNotice";
import { useSession } from "@/features/auth/SessionProvider";
import { maskPhone } from "@/lib/format/phone";

import { usePatientApi } from "./api";
import { ageText, looksLikePhone, SEX_LABELS, type Patient } from "./fields";
import { patientPath } from "./RegisterPatientDrawer";
import { useRegisterPatient } from "./RegisterPatientProvider";

type Load =
  | { readonly status: "loading" }
  | { readonly status: "done"; readonly items: readonly Patient[] }
  | { readonly status: "failed"; readonly error: unknown };

/**
 * The matches for a lookup text (`/patients?q=`), when Enter is pressed in the
 * search without choosing a match. A lookup, not a list of every patient: the API
 * returns at most 20, by phone, code or the start of a name (spec R5).
 */
export function PatientResults({ q }: { q: string }) {
  const { endSession } = useSession();
  const api = usePatientApi();
  const openRegister = useRegisterPatient();
  const [load, setLoad] = useState<Load>({ status: "loading" });
  const [attempt, setAttempt] = useState(0);
  const text = q.trim();

  useEffect(() => {
    if (text === "") return;
    let cancelled = false;
    api.lookup(text).then(
      (items) => {
        if (!cancelled) setLoad({ status: "done", items });
      },
      (error: unknown) => {
        if (!cancelled && !endSession(error)) setLoad({ status: "failed", error });
      },
    );
    return () => {
      cancelled = true;
    };
  }, [text, api, attempt, endSession]);

  const register = openRegister === null ? null : () => openRegister(looksLikePhone(text) ? { phone: text } : {});

  return (
    <section aria-labelledby="patients-heading" className="space-y-4">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div className="min-w-0">
          <h1 id="patients-heading" className="heading-5 text-slate-900">
            Patients
          </h1>
          {text !== "" && <p className="mt-1 break-words text-slate-700">Matches for “{text}”, by phone, code or the start of a name</p>}
        </div>
        {register !== null && (
          <Button variant="primary" onClick={register} icon={<UserPlus className="size-4" />}>
            Register patient
          </Button>
        )}
      </div>

      {text === "" ? (
        <EmptyState icon={<Search className="size-5" />} title="Find a patient">
          <p className="text-lg">Find a patient with the search above (press /): a phone number, a patient code or the start of a name.</p>
        </EmptyState>
      ) : load.status === "loading" ? (
        <ListSkeleton label="Searching…" rows={3} />
      ) : load.status === "failed" ? (
        <ErrorNotice
          error={load.error}
          onRetry={() => {
            setLoad({ status: "loading" });
            setAttempt((n) => n + 1);
          }}
        />
      ) : load.items.length === 0 ? (
        <EmptyState
          icon={<SearchX className="size-5" />}
          title={`No patient matches “${text}”.`}
          {...(register === null
            ? {}
            : {
                action: (
                  <Button onClick={register} icon={<UserPlus className="size-4" />}>
                    Register a new patient
                  </Button>
                ),
              })}
        >
          <p role="status">Check the spelling, try the phone number or the code, or register the patient.</p>
        </EmptyState>
      ) : (
        <div className={TABLE_WRAP}>
          <table role="table" className={TABLE}>
            <caption className="sr-only">Patients matching “{text}”</caption>
            <thead role="rowgroup">
              <tr role="row">
                <th role="columnheader" scope="col" className={TH}>Name</th>
                <th role="columnheader" scope="col" className={TH}>Code</th>
                <th role="columnheader" scope="col" className={TH}>Age</th>
                <th role="columnheader" scope="col" className={TH}>Sex</th>
                <th role="columnheader" scope="col" className={TH}>Phone</th>
              </tr>
            </thead>
            <tbody role="rowgroup">
              {load.items.map((patient) => (
                <tr role="row" key={patient.id} className={TR}>
                  <td role="cell" data-label="" className={TD}>
                    <span className="flex items-center gap-3">
                      <Avatar name={patient.full_name} size="sm" />
                      <Link
                        href={patientPath(patient.id)}
                        className="min-w-0 break-words font-semibold text-brand-800 underline-offset-2 hover:underline max-md:inline-flex max-md:min-h-11 max-md:items-center"
                      >
                        {patient.full_name}
                      </Link>
                    </span>
                  </td>
                  <td role="cell" data-label="Code" className={`${TD} tabular-nums`}>{patient.code}</td>
                  <td role="cell" data-label="Age" className={TD}>{ageText(patient)}</td>
                  <td role="cell" data-label="Sex" className={TD}>{SEX_LABELS[patient.sex]}</td>
                  <td role="cell" data-label="Phone" className={`${TD} tabular-nums`}>{maskPhone(patient.phone_e164)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}