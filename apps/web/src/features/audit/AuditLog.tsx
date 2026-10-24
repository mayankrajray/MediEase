"use client";

import { useEffect, useId, useState, type FormEvent } from "react";

import { Button } from "@/components/ui/Button";
import { EmptyState } from "@/components/ui/EmptyState";
import { INPUT, LABEL } from "@/components/ui/Field";
import { PageHeader } from "@/components/ui/PageHeader";
import { Skeleton } from "@/components/ui/Skeleton";
import { TABLE, TABLE_WRAP, TD, TH, TR } from "@/components/ui/table";
import { ROLE_LABELS } from "@/features/auth/labels";
import { ErrorNotice } from "@/features/auth/ErrorNotice";
import type { Role } from "@/features/auth/landing";
import { useSession } from "@/features/auth/SessionProvider";
import { clinicToday } from "@/features/patients/fields";
import { useClinic } from "@/features/shell/ClinicGate";
import { addDays, formatDateTime } from "@/lib/format/time";

import { useAuditApi, type AuditCategory, type AuditEntry, type AuditPage, type AuditQuery } from "./api";

type Load =
  | { readonly status: "loading" }
  | { readonly status: "ready"; readonly page: AuditPage; readonly items: readonly AuditEntry[] }
  | { readonly status: "failed"; readonly error: unknown };

/** "cancel_reason: PATIENT_REQUEST · on_date: 2026-10-24": IDs, codes and enums only. */
function details(metadata: Readonly<Record<string, string>>): string {
  return Object.entries(metadata)
    .sort(([a], [b]) => a.localeCompare(b))
    .map(([k, v]) => `${k.replaceAll("_", " ")}: ${v}`)
    .join(" · ");
}

function record(entry: AuditEntry): string {
  if (entry.patient_code !== null) return `Patient ${entry.patient_code}`;
  return entry.entity_type === null ? "–" : entry.entity_type.replaceAll("_", " ");
}

/**
 * The clinic's audit log for its owners (M6a-P8, FR-AUD-03, decision 8A): who did what and when,
 * newest first, 50 at a time, by day range (the last 7 days unless chosen; at most 92) and
 * category. *Export CSV* downloads the whole range; the export is itself recorded here.
 */
export function AuditLog() {
  const clinic = useClinic();
  const api = useAuditApi();
  const { clinic: choice, endSession } = useSession();
  const allowed = choice.kind === "active" && choice.membership.permissions.includes("AUDIT_VIEW");
  const today = clinicToday(clinic.timezone);
  const [from, setFrom] = useState(addDays(today, -6));
  const [to, setTo] = useState(today);
  const [category, setCategory] = useState<AuditCategory | "">("");
  const [query, setQuery] = useState<AuditQuery>({ from: addDays(today, -6), to: today });
  const [load, setLoad] = useState<Load>({ status: "loading" });
  const [attempt, setAttempt] = useState(0);
  const [more, setMore] = useState(false);
  const [exporting, setExporting] = useState(false);
  const [actionError, setActionError] = useState<unknown>(null);
  const [message, setMessage] = useState("");
  const ids = { from: useId(), to: useId(), category: useId() };

  useEffect(() => {
    if (!allowed) return;
    let cancelled = false;
    api.list(query).then(
      (page) => {
        if (!cancelled) setLoad({ status: "ready", page, items: page.items });
      },
      (failure: unknown) => {
        if (!cancelled && !endSession(failure)) setLoad({ status: "failed", error: failure });
      },
    );
    return () => {
      cancelled = true;
    };
  }, [api, query, attempt, allowed, endSession]);

  if (!allowed) {
    return (
      <section className="space-y-4">
        <PageHeader title="Audit log" />
        <p role="alert" className="rounded-card border border-amber-300 bg-amber-50 p-4 text-amber-950">
          The audit log is for the clinic&apos;s owners. Ask an owner if you need to know who changed something.
        </p>
      </section>
    );
  }

  function apply(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setMessage("");
    setLoad({ status: "loading" });
    setQuery({ from, to, ...(category === "" ? {} : { category }) });
  }

  async function loadMore() {
    if (load.status !== "ready" || load.page.next_cursor === null) return;
    setMore(true);
    setActionError(null);
    try {
      const next = await api.list({ ...query, cursor: load.page.next_cursor });
      setLoad({ status: "ready", page: next, items: [...load.items, ...next.items] });
    } catch (failure) {
      if (!endSession(failure)) setActionError(failure);
    } finally {
      setMore(false);
    }
  }

  async function exportCsv() {
    setExporting(true);
    setActionError(null);
    setMessage("");
    try {
      const file = await api.exportCsv(query.from, query.to);
      const url = URL.createObjectURL(file.blob);
      const link = document.createElement("a");
      link.href = url;
      link.download = file.filename;
      link.click();
      URL.revokeObjectURL(url);
      setMessage(`Exported ${file.filename}.`);
    } catch (failure) {
      if (!endSession(failure)) setActionError(failure);
    } finally {
      setExporting(false);
    }
  }

  const categories = load.status === "ready" ? load.page.categories : [];
  const labelOf = (value: string) => categories.find((c) => c.value === value)?.label ?? value;

  return (
    <section className="space-y-4">
      <PageHeader
        title="Audit log"
        description="Who did what in this clinic, newest first. Entries cannot be changed."
        actions={
          <Button onClick={() => void exportCsv()} disabled={exporting}>
            {exporting ? "Exporting…" : "Export CSV"}
          </Button>
        }
      />
      <form onSubmit={apply} className="flex flex-wrap items-end gap-3" aria-label="Filter the audit log">
        <div>
          <label htmlFor={ids.from} className={LABEL}>
            From
          </label>
          <input id={ids.from} type="date" value={from} max={to} onChange={(e) => setFrom(e.target.value)} className={INPUT} />
        </div>
        <div>
          <label htmlFor={ids.to} className={LABEL}>
            To
          </label>
          <input id={ids.to} type="date" value={to} min={from} max={today} onChange={(e) => setTo(e.target.value)} className={INPUT} />
        </div>
        <div>
          <label htmlFor={ids.category} className={LABEL}>
            Category
          </label>
          <select
            id={ids.category}
            value={category}
            onChange={(e) => setCategory(e.target.value as AuditCategory | "")}
            className={INPUT}
          >
            <option value="">Everything</option>
            {categories.map((c) => (
              <option key={c.value} value={c.value}>
                {c.label}
              </option>
            ))}
          </select>
        </div>
        <Button type="submit" variant="primary">
          Show
        </Button>
      </form>
      <p className="text-sm text-slate-700">Up to 92 days at a time. Times are the clinic&apos;s ({clinic.timezone}).</p>
      <p role="status" aria-live="polite" className={message === "" ? "sr-only" : "font-medium text-emerald-900"}>
        {load.status === "loading" ? "Loading the audit log…" : message}
      </p>
      {actionError !== null && <ErrorNotice error={actionError} />}
      {load.status === "loading" && <Skeleton className="h-64" />}
      {load.status === "failed" && (
        <ErrorNotice
          error={load.error}
          onRetry={() => {
            setLoad({ status: "loading" });
            setAttempt((n) => n + 1);
          }}
        />
      )}
      {load.status === "ready" && load.items.length === 0 && (
        <EmptyState title="Nothing recorded in this range">Try a longer range or another category.</EmptyState>
      )}
      {load.status === "ready" && load.items.length > 0 && (
        <>
          <div className={TABLE_WRAP}>
            <table role="table" className={TABLE}>
              <caption className="sr-only">Audit log entries, newest first</caption>
              <thead role="rowgroup">
                <tr role="row">
                  <th role="columnheader" scope="col" className={TH}>When</th>
                  <th role="columnheader" scope="col" className={TH}>Who</th>
                  <th role="columnheader" scope="col" className={TH}>What</th>
                  <th role="columnheader" scope="col" className={TH}>Record</th>
                  <th role="columnheader" scope="col" className={TH}>Details</th>
                </tr>
              </thead>
              <tbody role="rowgroup">
                {load.items.map((entry) => (
                  <tr key={entry.id} role="row" className={TR}>
                    <td role="cell" className={`${TD} whitespace-nowrap`} data-label="When">
                      {formatDateTime(entry.occurred_at, clinic.timezone)}
                    </td>
                    <td role="cell" className={TD} data-label="Who">
                      <span className="font-medium">{entry.actor.label}</span>
                      {entry.actor.role !== null && (
                        <span className="block text-sm text-slate-700">{ROLE_LABELS[entry.actor.role as Role]}</span>
                      )}
                    </td>
                    <td role="cell" className={TD} data-label="What">
                      {entry.action_label}
                      <span className="block text-sm text-slate-700">{labelOf(entry.category)}</span>
                    </td>
                    <td role="cell" className={TD} data-label="Record">
                      {record(entry)}
                    </td>
                    <td role="cell" className={`${TD} text-sm text-slate-700`} data-label="Details">
                      {details(entry.metadata)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          {load.page.next_cursor !== null && (
            <Button onClick={() => void loadMore()} disabled={more}>
              {more ? "Loading…" : "Load more"}
            </Button>
          )}
        </>
      )}
    </section>
  );
}
