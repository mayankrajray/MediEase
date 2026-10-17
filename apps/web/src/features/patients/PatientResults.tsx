"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

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
        <h1 id="patients-heading" className="text-2xl font-bold">
          Patients
        </h1>
        {register !== null && (
          <button
            type="button"
            onClick={register}
            className="rounded bg-blue-800 px-4 py-2 font-semibold text-white hover:bg-blue-900"
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
        <table className="w-full border-collapse text-left">
          <caption className="sr-only">Patients matching “{text}”</caption>
          <thead>
            <tr className="border-b border-slate-400">
              <th scope="col" className="py-2 pr-4">Name</th>
              <th scope="col" className="py-2 pr-4">Code</th>
              <th scope="col" className="py-2 pr-4">Age</th>
              <th scope="col" className="py-2 pr-4">Sex</th>
              <th scope="col" className="py-2">Phone</th>
            </tr>
          </thead>
          <tbody>
            {load.items.map((patient) => (
              <tr key={patient.id} className="border-b border-slate-200">
                <td className="py-2 pr-4">
                  <Link href={patientPath(patient.id)} className="font-semibold text-blue-900 underline">
                    {patient.full_name}
                  </Link>
                </td>
                <td className="py-2 pr-4">{patient.code}</td>
                <td className="py-2 pr-4">{ageText(patient)}</td>
                <td className="py-2 pr-4">{SEX_LABELS[patient.sex]}</td>
                <td className="py-2">{maskPhone(patient.phone_e164)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      )}
    </section>
  );
}
