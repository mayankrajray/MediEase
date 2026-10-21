"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

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
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h1 id="patients-heading" className="text-2xl font-bold tracking-tight">
          Patients
        </h1>
        {register !== null && (
          <button
            type="button"
            onClick={register}
            className="inline-flex min-h-10 items-center justify-center gap-2 rounded-lg bg-brand-700 px-4 py-2 font-medium text-white transition-colors hover:bg-brand-800 disabled:cursor-not-allowed disabled:bg-slate-400 motion-reduce:transition-none"
          >
            Register patient
          </button>
        )}
      </div>

      {text === "" ? (
        <p className="text-lg">Find a patient with the search above (press /): a phone number, a patient code or the start of a name.</p>
      ) : load.status === "loading" ? (
        <p role="status" className="text-slate-700">
          Searching…
        </p>
      ) : load.status === "failed" ? (
        <ErrorNotice
          error={load.error}
          onRetry={() => {
            setLoad({ status: "loading" });
            setAttempt((n) => n + 1);
          }}
        />
      ) : load.items.length === 0 ? (
        <p role="status" className="text-lg">
          No patient matches “{text}”.
        </p>
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
                    <Link href={patientPath(patient.id)} className="font-semibold text-brand-800 underline-offset-2 hover:underline">
                      {patient.full_name}
                    </Link>
                  </td>
                  <td role="cell" data-label="Code" className={TD}>{patient.code}</td>
                  <td role="cell" data-label="Age" className={TD}>{ageText(patient)}</td>
                  <td role="cell" data-label="Sex" className={TD}>{SEX_LABELS[patient.sex]}</td>
                  <td role="cell" data-label="Phone" className={TD}>{maskPhone(patient.phone_e164)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}
