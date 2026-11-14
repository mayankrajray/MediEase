"use client";

import { Activity, ChevronDown, Download, RotateCw } from "lucide-react";
import Link from "next/link";
import { Fragment, useEffect, useId, useMemo, useState } from "react";

import { Button, buttonClasses } from "@/components/ui/Button";
import { cx } from "@/components/ui/cx";
import { EmptyState } from "@/components/ui/EmptyState";
import { KeyValue } from "@/components/ui/KeyValue";
import { m, STAGGER } from "@/components/ui/Motion";
import { PageHeader } from "@/components/ui/PageHeader";
import { Segmented } from "@/components/ui/Segmented";
import { ListSkeleton, Skeleton } from "@/components/ui/Skeleton";
import { STAT_STRIP, StatTile } from "@/components/ui/StatTile";
import { StatusBadge, type Tone } from "@/components/ui/StatusBadge";
import { TABLE, TABLE_WRAP, TD, TH, TR } from "@/components/ui/table";
import { ErrorNotice } from "@/features/auth/ErrorNotice";
import { useSession } from "@/features/auth/SessionProvider";
import { sessionGet } from "@/lib/auth/refresh";
import { formatDateTime } from "@/lib/format/time";

import {
  byActivity,
  downloadCsv,
  formatCount,
  inWeeks,
  lastActiveLabel,
  METRICS,
  type Usage,
  type UsageRow,
  usageCsv,
  weekLabel,
} from "./usage";

type Load =
  | { readonly status: "loading" }
  | { readonly status: "ready"; readonly usage: Usage }
  | { readonly status: "failed"; readonly error: unknown };

type Weeks = "4" | "8" | "12";

const WEEK_OPTIONS: readonly { readonly value: Weeks; readonly label: string }[] = [
  { value: "4", label: "4 weeks" },
  { value: "8", label: "8 weeks" },
  { value: "12", label: "12 weeks" },
];

const STATUS: Record<UsageRow["status"], { readonly label: string; readonly tone: Tone }> = {
  ACTIVE: { label: "Active", tone: "done" },
  ONBOARDING: { label: "Setting up", tone: "waiting" },
  SUSPENDED: { label: "Suspended", tone: "danger" },
};

const today = () => new Date().toISOString().slice(0, 10);

/**
 * M9-P4 (FR-OPS-03; spec ops-clinic-usage): how each clinic uses MediEase. A summary of the
 * weeks shown, then one row per clinic, active ones first: last use, the people working there,
 * visits each week, prescriptions and delivery health; "Details" opens the week-by-week counts
 * and a CSV of them for that clinic (the design partners' usage evidence). Counts only.
 */
export function ClinicUsage() {
  const { endSession } = useSession();
  const [weeks, setWeeks] = useState<Weeks>("4");
  const [load, setLoad] = useState<Load>({ status: "loading" });
  const [attempt, setAttempt] = useState(0);

  useEffect(() => {
    let cancelled = false;
    sessionGet("/api/v1/ops/clinic-usage", { query: { weeks } }).then(
      ({ data }) => {
        if (!cancelled) setLoad({ status: "ready", usage: data });
      },
      (failure: unknown) => {
        if (!cancelled && !endSession(failure)) setLoad({ status: "failed", error: failure });
      },
    );
    return () => {
      cancelled = true;
    };
  }, [weeks, attempt, endSession]);

  const reload = () => {
    setLoad({ status: "loading" });
    setAttempt((n) => n + 1);
  };
  const usage = load.status === "ready" ? load.usage : null;
  const rows = useMemo(() => (usage === null ? [] : [...usage.clinics].sort(byActivity)), [usage]);

  return (
    <div>
      <PageHeader
        title="Clinic usage"
        description={
          usage === null
            ? "How each clinic uses MediEase, week by week. Counts only, no patient details."
            : `How each clinic uses MediEase, week by week. Counts only, no patient details. Updated ${formatDateTime(usage.generated_at, "Asia/Kolkata")}.`
        }
        actions={
          <>
            <Segmented
              label="Weeks shown"
              options={WEEK_OPTIONS}
              value={weeks}
              onChange={(value) => {
                if (value === weeks) return;
                setLoad({ status: "loading" });
                setWeeks(value);
              }}
            />
            <Button variant="ghost" onClick={reload} icon={<RotateCw className="size-4" />} disabled={load.status === "loading"}>
              Refresh
            </Button>
            <Button
              onClick={() => usage !== null && downloadCsv(`mediease-usage-all-clinics-${today()}.csv`, usageCsv(usage, rows))}
              icon={<Download className="size-4" />}
              disabled={usage === null || rows.length === 0}
            >
              Download CSV
            </Button>
          </>
        }
      />

      {load.status === "loading" && <UsageSkeleton />}
      {load.status === "failed" && (
        <div className="max-w-xl">
          <ErrorNotice error={load.error} onRetry={reload} />
        </div>
      )}
      {usage !== null && rows.length === 0 && (
        <EmptyState
          icon={<Activity className="size-5" />}
          title="No clinics yet"
          action={
            <Link href="/ops/clinics/new" className={buttonClasses("primary")}>
              Create clinic
            </Link>
          }
        >
          <p>Each clinic’s patients, visits and prescriptions appear here once it starts working in MediEase.</p>
        </EmptyState>
      )}
      {usage !== null && rows.length > 0 && (
        <div className="space-y-6">
          <Summary usage={usage} />
          <UsageTable usage={usage} rows={rows} />
        </div>
      )}
    </div>
  );
}

function UsageSkeleton() {
  return (
    <div className="space-y-6">
      <div aria-hidden="true" className={cx(STAT_STRIP, "grid-cols-2 md:grid-cols-5")}>
        {Array.from({ length: 5 }, (_, i) => (
          <div key={i} className="bg-surface px-4 py-3.5">
            <Skeleton className="h-4 w-24" />
            <Skeleton className="mt-2 h-8 w-14" />
          </div>
        ))}
      </div>
      <ListSkeleton label="Loading clinic usage" rows={4} />
    </div>
  );
}

function Summary({ usage }: { usage: Usage }) {
  const span = usage.weeks.length === 1 ? "This week" : `Last ${usage.weeks.length} weeks`;
  const { summary } = usage;
  return (
    <m.ul
      aria-label={`All clinics, ${span.toLowerCase()}`}
      variants={STAGGER}
      initial="hidden"
      animate="shown"
      className={cx(STAT_STRIP, "grid-cols-2 md:grid-cols-5 max-md:[&>li:last-child]:col-span-2")}
    >
      <StatTile
        layout="segment"
        tone={summary.active_clinics > 0 ? "done" : "neutral"}
        label="Active clinics"
        value={`${summary.active_clinics} of ${summary.clinics}`}
        hint="Used in the last 7 days"
      />
      <StatTile layout="segment" tone="brand" label="Patients registered" value={formatCount(summary.totals.patients)} hint={span} />
      <StatTile layout="segment" tone="brand" label="Visits" value={formatCount(summary.totals.visits)} hint={span} />
      <StatTile layout="segment" tone="brand" label="Prescriptions issued" value={formatCount(summary.totals.prescriptions)} hint={span} />
      <StatTile layout="segment" tone="brand" label="Bills issued" value={formatCount(summary.totals.bills)} hint={span} />
    </m.ul>
  );
}

function UsageTable({ usage, rows }: { usage: Usage; rows: readonly UsageRow[] }) {
  const [open, setOpen] = useState<string | null>(null);
  const span = usage.weeks.length === 1 ? "this week" : `last ${usage.weeks.length} weeks`;
  return (
    <div className={TABLE_WRAP}>
      <table role="table" className={TABLE}>
        <caption className="sr-only">Each clinic’s usage, active clinics first</caption>
        <thead role="rowgroup">
          <tr role="row">
            <th role="columnheader" scope="col" className={TH}>Clinic</th>
            <th role="columnheader" scope="col" className={TH}>Last active</th>
            <th role="columnheader" scope="col" className={TH}>People</th>
            <th role="columnheader" scope="col" className={TH}>Visits by week</th>
            <th role="columnheader" scope="col" className={cx(TH, "text-right")}>Prescriptions</th>
            <th role="columnheader" scope="col" className={TH}>Delivery</th>
            <th role="columnheader" scope="col" className={TH}>
              <span className="sr-only">Details</span>
            </th>
          </tr>
        </thead>
        <tbody role="rowgroup">
          {rows.map((row) => (
            <ClinicRow
              key={row.clinic_id}
              row={row}
              usage={usage}
              span={span}
              open={open === row.clinic_id}
              onToggle={() => setOpen((current) => (current === row.clinic_id ? null : row.clinic_id))}
            />
          ))}
        </tbody>
      </table>
    </div>
  );
}

function ClinicRow({
  row,
  usage,
  span,
  open,
  onToggle,
}: {
  row: UsageRow;
  usage: Usage;
  span: string;
  open: boolean;
  onToggle: () => void;
}) {
  const detailId = useId();
  const status = STATUS[row.status];
  const people = row.staff.members;
  return (
    <Fragment>
      <tr role="row" className={cx(TR, open && "md:bg-brand-50/40")}>
        <th role="rowheader" scope="row" className={cx(TD, "font-medium")}>
          <span className="block text-slate-900">{row.name}</span>
          <span className="mt-1 flex flex-wrap items-center gap-2">
            <StatusBadge tone={status.tone}>{status.label}</StatusBadge>
            <span className="font-mono text-sm font-normal text-slate-600">{row.slug}</span>
          </span>
        </th>
        <td role="cell" data-label="Last active" className={TD}>
          {row.last_active_at === null ? (
            <span className="text-slate-700">Not used yet</span>
          ) : (
            <span className="block tabular-nums text-slate-900">{lastActiveLabel(row.last_active_at, row.timezone)}</span>
          )}
          <span className="mt-0.5 flex items-center gap-1.5 text-sm text-slate-700">
            <span aria-hidden="true" className={cx("size-2 rounded-full", row.active_this_week ? "bg-emerald-600" : "bg-slate-400")} />
            {row.active_this_week ? "Active this week" : "Quiet this week"}
          </span>
        </td>
        <td role="cell" data-label="People" className={TD}>
          <span className="block tabular-nums text-slate-900">
            {people} {people === 1 ? "person" : "people"}
          </span>
          <span className="mt-0.5 block text-sm text-slate-700">{row.staff.active_7d} active in 7 days</span>
        </td>
        <td role="cell" data-label="Visits by week" className={TD}>
          <WeekBars row={row} usage={usage} />
        </td>
        <td role="cell" data-label="Prescriptions" className={cx(TD, "md:text-right")}>
          <span className="block font-semibold tabular-nums text-slate-900">{formatCount(inWeeks(row, "prescriptions"))}</span>
          <span className="block text-sm text-slate-700">{span}</span>
        </td>
        <td role="cell" data-label="Delivery" className={TD}>
          <Health row={row} />
        </td>
        <td role="cell" data-label="" className={cx(TD, "md:text-right")}>
          <Button
            variant="ghost"
            size="sm"
            aria-expanded={open}
            aria-controls={open ? detailId : undefined}
            aria-label={`${open ? "Hide" : "Details"} for ${row.name}`}
            onClick={onToggle}
            icon={<ChevronDown className={cx("size-4 transition-transform duration-200 ease-brand motion-reduce:transition-none", open && "rotate-180")} />}
          >
            {open ? "Hide" : "Details"}
          </Button>
        </td>
      </tr>
      {open && (
        <tr role="row" id={detailId} className="md:border-b md:border-slate-100">
          <td role="cell" data-label="" colSpan={7} className="md:px-3 md:pb-5 md:pt-1">
            <ClinicDetail row={row} usage={usage} />
          </td>
        </tr>
      )}
    </Fragment>
  );
}

/** Visits in each week shown, as bars with their numbers; the numbers carry it, not the bars. */
function WeekBars({ row, usage }: { row: UsageRow; usage: Usage }) {
  const counts = row.weeks.map((w) => w.counts.visits);
  const most = Math.max(1, ...counts);
  const total = counts.reduce((a, b) => a + b, 0);
  const labelled = row.weeks.length <= 4;
  return (
    <div className="flex items-end gap-3">
      <div aria-hidden="true" className="flex h-12 items-end gap-1.5">
        {row.weeks.map((week, i) => {
          const n = week.counts.visits;
          const current = i === row.weeks.length - 1;
          return (
            <div key={week.start} className="flex h-full flex-col items-center justify-end gap-0.5">
              {labelled && <span className="text-xs font-semibold tabular-nums leading-none text-slate-700">{n}</span>}
              <span
                className={cx(
                  "block w-3 rounded-t-sm",
                  n === 0 ? "h-px bg-slate-300" : current ? "bg-brand-700" : "bg-brand-500",
                )}
                style={n === 0 ? undefined : { height: `${Math.max(3, Math.round((n / most) * (labelled ? 30 : 40)))}px` }}
              />
            </div>
          );
        })}
      </div>
      <span className="text-sm text-slate-700">
        <span className="block font-semibold tabular-nums text-slate-900">{formatCount(total)}</span>
        visits
      </span>
      <span className="sr-only">
        Visits by week, oldest first: {row.weeks.map((w, i) => `${weekLabel(usage.weeks[i]?.start ?? w.start)}: ${w.counts.visits}`).join("; ")}
      </span>
    </div>
  );
}

function Health({ row }: { row: UsageRow }) {
  const { failed_messages_7d: failed, failed_jobs_7d: jobs, not_sent_7d: held } = row.health;
  if (failed + jobs > 0) {
    const parts = [failed > 0 && `${failed} message${failed === 1 ? "" : "s"}`, jobs > 0 && `${jobs} job${jobs === 1 ? "" : "s"}`].filter(Boolean);
    return (
      <>
        <StatusBadge tone="danger">{parts.join(", ")} failed</StatusBadge>
        <span className="mt-1 block text-sm text-slate-700">In the last 7 days</span>
      </>
    );
  }
  if (held > 0) {
    return (
      <>
        <StatusBadge tone="neutral">{held} not sent</StatusBadge>
        <span className="mt-1 block text-sm text-slate-700">WhatsApp is switched off</span>
      </>
    );
  }
  return <StatusBadge tone="done">No problems</StatusBadge>;
}

function ClinicDetail({ row, usage }: { row: UsageRow; usage: Usage }) {
  const lastWeek = row.weeks.length - 1;
  return (
    <div className="rounded-card border border-line bg-surface p-4 shadow-card max-md:mt-2 sm:p-5">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <h3 className="text-base font-semibold text-slate-900">{row.name}, week by week</h3>
        <Button
          size="sm"
          icon={<Download className="size-4" />}
          aria-label={`Download CSV for ${row.name}`}
          onClick={() => downloadCsv(`mediease-usage-${row.slug}-${today()}.csv`, usageCsv(usage, [row]))}
        >
          Download CSV
        </Button>
      </div>

      <KeyValue
        className="mt-4 md:grid-cols-4"
        items={[
          { label: "On MediEase since", value: formatDateTime(row.created_at, row.timezone).split(",")[0] },
          { label: "Owners", value: row.staff.owners },
          { label: "Doctors", value: row.staff.doctors },
          { label: "Front desk", value: row.staff.front_desk },
        ]}
      />

      <div className="mt-5 overflow-x-auto">
        <table className="w-full min-w-[34rem] text-left text-sm">
          <caption className="sr-only">
            {row.name}: records made each week, oldest first, and all time
          </caption>
          <thead className="bg-surface-muted text-slate-700">
            <tr>
              <th scope="col" className="px-2 py-2 font-semibold">Week</th>
              {METRICS.map((metric) => (
                <th key={metric.key} scope="col" className="px-2 py-2 text-right font-semibold">
                  {metric.short}
                </th>
              ))}
            </tr>
          </thead>
          <tbody className="divide-y divide-line tabular-nums">
            {row.weeks.map((week, i) => (
              <tr key={week.start}>
                <th scope="row" className="px-2 py-2 font-medium text-slate-900">
                  {weekLabel(usage.weeks[i]?.start ?? week.start)}
                  {i === lastWeek && (
                    <>
                      {" "}
                      <span className="font-normal text-slate-600">(this week)</span>
                    </>
                  )}
                </th>
                {METRICS.map((metric) => (
                  <td key={metric.key} className={cx("px-2 py-2 text-right", week.counts[metric.key] === 0 ? "text-slate-500" : "text-slate-900")}>
                    {formatCount(week.counts[metric.key])}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
          <tfoot className="border-t-2 border-line tabular-nums">
            <tr>
              <th scope="row" className="px-2 py-2 font-semibold text-slate-900">All time</th>
              {METRICS.map((metric) => (
                <td key={metric.key} className="px-2 py-2 text-right font-semibold text-slate-900">
                  {formatCount(row.totals[metric.key])}
                </td>
              ))}
            </tr>
          </tfoot>
        </table>
      </div>
    </div>
  );
}
