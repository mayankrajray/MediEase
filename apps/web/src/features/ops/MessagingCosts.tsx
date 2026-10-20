"use client";

import { useEffect, useId, useState } from "react";

import { ErrorNotice } from "@/features/auth/ErrorNotice";
import { useSession } from "@/features/auth/SessionProvider";
import { CHANNEL_LABELS } from "@/features/reminders/labels";
import type { GetResponse } from "@/lib/api/client";
import { sessionGet } from "@/lib/auth/refresh";
import { formatPaise } from "@/lib/format/money";

type Costs = GetResponse<"/api/v1/ops/messaging-costs">;
type ClinicCost = Costs["clinics"][number];

type Load =
  | { readonly status: "loading" }
  | { readonly status: "ready"; readonly costs: Costs }
  | { readonly status: "failed"; readonly error: unknown };

/** This month in India: the pilot runs in one region (M5-P6 decision 6A). */
export function currentMonth(now: Date = new Date()): string {
  const parts = new Intl.DateTimeFormat("en-CA", { timeZone: "Asia/Kolkata", year: "numeric", month: "2-digit" }).formatToParts(now);
  const part = (type: string) => parts.find((p) => p.type === type)?.value ?? "";
  return `${part("year")}-${part("month")}`;
}

const MONTH = /^\d{4}-(0[1-9]|1[0-2])$/;

/**
 * What each clinic's messages cost in a month (spec R18; M5-P5 decision 7A, M5-P6 6A): messages,
 * how many are not priced yet, and the cost in rupees excluding GST, with a row per channel.
 * Counts and money only.
 */
export function MessagingCosts() {
  const { endSession } = useSession();
  const [month, setMonth] = useState(currentMonth);
  const [load, setLoad] = useState<Load>({ status: "loading" });
  const [attempt, setAttempt] = useState(0);
  const monthId = useId();

  useEffect(() => {
    if (!MONTH.test(month)) return;
    let cancelled = false;
    sessionGet("/api/v1/ops/messaging-costs", { query: { month } }).then(
      ({ data }) => {
        if (!cancelled) setLoad({ status: "ready", costs: data });
      },
      (failure: unknown) => {
        if (!cancelled && !endSession(failure)) setLoad({ status: "failed", error: failure });
      },
    );
    return () => {
      cancelled = true;
    };
  }, [month, attempt, endSession]);

  return (
    <section aria-labelledby="costs-heading" className="space-y-4">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 id="costs-heading" className="text-2xl font-bold">
            Messaging costs
          </h1>
          <p className="text-slate-800">Per clinic, excluding GST. A message is priced once its delivery is reported.</p>
        </div>
        <div>
          <label htmlFor={monthId} className="block font-medium">
            Month
          </label>
          <input
            id={monthId}
            type="month"
            value={month}
            onChange={(event) => {
              if (!MONTH.test(event.target.value)) return;
              setLoad({ status: "loading" });
              setMonth(event.target.value);
            }}
            className="rounded border border-slate-500 px-2 py-1.5"
          />
        </div>
      </div>

      {load.status === "loading" && (
        <p role="status" className="text-slate-700">
          Loading costs…
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
      {load.status === "ready" && load.costs.clinics.length === 0 && (
        <p className="text-lg">No messages were sent in this month.</p>
      )}
      {load.status === "ready" && load.costs.clinics.length > 0 && (
        <>
          <p className="text-lg font-semibold">Total: {formatPaise(load.costs.cost_paise)}</p>
          <div className="overflow-x-auto">
            <table className="w-full border-collapse text-left">
              <caption className="sr-only">Messaging costs per clinic and channel</caption>
              <thead>
                <tr className="border-b border-slate-400">
                  <th scope="col" className="py-2 pr-4">Clinic</th>
                  <th scope="col" className="py-2 pr-4">Channel</th>
                  <th scope="col" className="py-2 pr-4">Messages</th>
                  <th scope="col" className="py-2 pr-4">Not priced yet</th>
                  <th scope="col" className="py-2">Cost</th>
                </tr>
              </thead>
              <tbody>
                {load.costs.clinics.map((clinic) => (
                  <ClinicRows key={clinic.clinic_id} clinic={clinic} />
                ))}
              </tbody>
            </table>
          </div>
          <p className="text-sm text-slate-700">
            “Not priced yet” counts messages whose delivery has not been reported, or whose price is not known; they are not in
            the cost.
          </p>
        </>
      )}
    </section>
  );
}

function ClinicRows({ clinic }: Readonly<{ clinic: ClinicCost }>) {
  return (
    <>
      <tr className="border-t border-slate-400 font-semibold">
        <th scope="row" className="py-2 pr-4">
          {clinic.clinic_name}
        </th>
        <td className="py-2 pr-4">All</td>
        <td className="py-2 pr-4">{clinic.messages}</td>
        <td className="py-2 pr-4">{clinic.unpriced}</td>
        <td className="py-2">{formatPaise(clinic.cost_paise)}</td>
      </tr>
      {clinic.channels.map((c) => (
        <tr key={c.channel} className="border-t border-slate-200">
          <td className="py-1 pr-4">
            <span className="sr-only">{clinic.clinic_name}</span>
          </td>
          <th scope="row" className="py-1 pr-4 font-normal">
            {CHANNEL_LABELS[c.channel]}
          </th>
          <td className="py-1 pr-4">{c.messages}</td>
          <td className="py-1 pr-4">{c.unpriced}</td>
          <td className="py-1">{formatPaise(c.cost_paise)}</td>
        </tr>
      ))}
    </>
  );
}
