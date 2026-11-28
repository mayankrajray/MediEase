"use client";

import { Download, FileUp, RotateCcw, Upload } from "lucide-react";
import Link from "next/link";
import { type RefObject, useEffect, useId, useRef, useState } from "react";

import { Alert } from "@/components/ui/Alert";
import { Breadcrumbs } from "@/components/ui/Breadcrumbs";
import { Button, buttonClasses } from "@/components/ui/Button";
import { cx } from "@/components/ui/cx";
import { PageHeader } from "@/components/ui/PageHeader";
import { Skeleton } from "@/components/ui/Skeleton";
import { STAT_STRIP, StatTile } from "@/components/ui/StatTile";
import { TABLE, TABLE_WRAP, TD, TH, TR } from "@/components/ui/table";
import { ErrorNotice } from "@/features/auth/ErrorNotice";
import { useSession } from "@/features/auth/SessionProvider";
import { ApiError, type GetResponse } from "@/lib/api/client";
import { sessionGet, sessionPostRaw } from "@/lib/auth/refresh";

import {
  codeRange,
  COLUMNS,
  duplicateText,
  FIELD_LABEL,
  fileProblem,
  type ImportReport,
  importable,
  MAX_IMPORT_ROWS,
  plural,
  problemText,
  TEMPLATE_CSV,
} from "./patientImportReport";
import { downloadCsv } from "./usage";

type Clinic = GetResponse<"/api/v1/ops/clinics/{clinic_id}">;
type ClinicLoad = { readonly status: "loading" } | { readonly status: "ready"; readonly clinic: Clinic } | { readonly status: "failed"; readonly error: unknown };
type Step =
  | { readonly kind: "idle" }
  | { readonly kind: "checking" }
  | { readonly kind: "checked"; readonly report: ImportReport }
  | { readonly kind: "importing"; readonly report: ImportReport }
  | { readonly kind: "done"; readonly report: ImportReport }
  | { readonly kind: "failed"; readonly error: unknown; readonly during: "check" | "import"; readonly report?: ImportReport };

const PATH = "/api/v1/ops/clinics/{clinic_id}/patient-imports";

/**
 * M9-P3 follow-up (FR-OPS-02, FR-PAT-08; spec patients R8): ops import a clinic's patient list.
 * The file is checked first (a dry run: nothing is saved); the report shows what would happen,
 * row by row; only "Import N patients" writes, and the API checks the file again as it does.
 * The report never holds a name or a phone, only row numbers, columns and counts.
 */
export function PatientImport({ clinicId }: { clinicId: string }) {
  const { endSession } = useSession();
  const [clinic, setClinic] = useState<ClinicLoad>({ status: "loading" });
  const [attempt, setAttempt] = useState(0);
  const [file, setFile] = useState<File | null>(null);
  const [problem, setProblem] = useState<string>();
  const [step, setStep] = useState<Step>({ kind: "idle" });
  const input = useRef<HTMLInputElement>(null);
  const result = useRef<HTMLElement>(null);
  const id = useId();

  useEffect(() => {
    let cancelled = false;
    sessionGet("/api/v1/ops/clinics/{clinic_id}", { pathParams: { clinic_id: clinicId } }).then(
      ({ data }) => {
        if (!cancelled) setClinic({ status: "ready", clinic: data });
      },
      (failure: unknown) => {
        if (!cancelled && !endSession(failure)) setClinic({ status: "failed", error: failure });
      },
    );
    return () => {
      cancelled = true;
    };
  }, [clinicId, attempt, endSession]);

  useEffect(() => {
    if (step.kind === "checked" || step.kind === "done") result.current?.focus();
  }, [step.kind]);

  function choose(chosen: File | null) {
    setFile(chosen);
    setProblem(chosen === null ? undefined : fileProblem(chosen));
    setStep({ kind: "idle" }); // a new file needs a new check
  }

  async function send(dryRun: boolean) {
    if (file === null) return;
    const previous = step.kind === "checked" ? step.report : undefined;
    setStep(dryRun ? { kind: "checking" } : { kind: "importing", report: previous as ImportReport });
    try {
      const { data } = await sessionPostRaw(PATH, file, "text/csv", {
        pathParams: { clinic_id: clinicId },
        query: { dry_run: dryRun ? "true" : "false" },
        timeoutMs: 60_000,
      });
      setStep(dryRun ? { kind: "checked", report: data } : { kind: "done", report: data });
    } catch (failure) {
      if (endSession(failure)) return;
      setStep({ kind: "failed", error: failure, during: dryRun ? "check" : "import", ...(previous ? { report: previous } : {}) });
    }
  }

  function startOver() {
    setFile(null);
    setProblem(undefined);
    setStep({ kind: "idle" });
    if (input.current !== null) input.current.value = "";
    input.current?.focus();
  }

  if (clinic.status === "loading") {
    return (
      <div className="space-y-4">
        <p role="status" className="sr-only">
          Loading the clinic
        </p>
        <Skeleton className="h-8 w-64" />
        <Skeleton className="h-40 w-full max-w-3xl" />
      </div>
    );
  }
  if (clinic.status === "failed") {
    return (
      <div className="max-w-xl space-y-4">
        <PageHeader title="Import patients" breadcrumbs={<Breadcrumbs items={[{ label: "Clinics", href: "/ops" }, { label: "Import patients" }]} />} />
        <ErrorNotice
          error={clinic.error}
          onRetry={() => {
            setClinic({ status: "loading" });
            setAttempt((n) => n + 1);
          }}
        />
      </div>
    );
  }

  const name = clinic.clinic.name;
  const busy = step.kind === "checking" || step.kind === "importing";
  const shown = step.kind === "checked" || step.kind === "importing" ? step.report : step.kind === "failed" ? step.report : undefined;

  return (
    <div className="max-w-5xl space-y-6">
      <PageHeader
        breadcrumbs={<Breadcrumbs items={[{ label: "Clinics", href: "/ops" }, { label: name }]} />}
        title="Import patients"
        description={`${name}. Check the clinic’s patient list first; nothing is saved until you choose Import.`}
      />

      {step.kind === "done" ? (
        <Done report={step.report} name={name} focus={result} onAgain={startOver} />
      ) : (
        <>
          <section aria-labelledby={`${id}-file`} className="rounded-card border border-line bg-surface p-4 shadow-card sm:p-5">
            <h2 id={`${id}-file`} className="heading-6 text-slate-900">
              Patient list
            </h2>
            <div className="mt-3 grid gap-4 md:grid-cols-[minmax(0,1fr)_minmax(0,18rem)]">
              <div className="space-y-2">
                <label htmlFor={`${id}-input`} className="block font-medium text-slate-900">
                  CSV file
                </label>
                <input
                  ref={input}
                  id={`${id}-input`}
                  type="file"
                  accept=".csv,text/csv"
                  disabled={busy}
                  aria-describedby={`${id}-help${problem !== undefined ? ` ${id}-problem` : ""}`}
                  aria-invalid={problem !== undefined}
                  onChange={(event) => choose(event.target.files?.[0] ?? null)}
                  className="block w-full text-sm text-slate-800 file:mr-3 file:min-h-10 file:cursor-pointer file:rounded-lg file:border file:border-slate-400 file:bg-white file:px-3 file:py-2 file:font-medium file:text-slate-900 hover:file:bg-slate-50"
                />
                <p id={`${id}-help`} className="text-sm text-slate-700">
                  Saved as CSV UTF-8 from Excel or Google Sheets, up to 2 MB and {MAX_IMPORT_ROWS.toLocaleString("en-IN")} rows.
                </p>
                {problem !== undefined && (
                  <p id={`${id}-problem`} role="alert" className="text-sm font-medium text-danger">
                    {problem}
                  </p>
                )}
              </div>
              <div className="rounded-lg bg-surface-muted p-3 text-sm text-slate-800">
                <p className="font-medium text-slate-900">Columns, in any order</p>
                <p className="mt-1 font-mono tabular-nums text-[13px] leading-6 break-words">{COLUMNS.join(", ")}</p>
                <Button
                  variant="ghost"
                  size="sm"
                  className="mt-2 -ml-2"
                  icon={<Download className="size-4" />}
                  onClick={() => downloadCsv("mediease-patients-template.csv", TEMPLATE_CSV)}
                >
                  Download a blank template
                </Button>
              </div>
            </div>
            <div className="mt-4 flex flex-wrap items-center gap-2">
              <Button
                variant={shown === undefined ? "primary" : "secondary"}
                icon={<FileUp className="size-4" />}
                loading={step.kind === "checking"}
                disabled={file === null || problem !== undefined || busy}
                onClick={() => void send(true)}
              >
                {step.kind === "checking" ? "Checking file…" : shown === undefined ? "Check file" : "Check again"}
              </Button>
              {file === null && <span className="text-sm text-slate-700">Choose a file to check it.</span>}
            </div>
          </section>

          {step.kind === "failed" && (
            <Failure error={step.error} during={step.during} onRetry={() => void send(step.during === "check")} />
          )}

          {shown !== undefined && (
            <Report
              report={shown}
              focus={result}
              importing={step.kind === "importing"}
              stale={step.kind === "failed"}
              onImport={() => void send(false)}
              onAgain={startOver}
            />
          )}
        </>
      )}
    </div>
  );
}

function Report({
  report,
  focus,
  importing,
  stale,
  onImport,
  onAgain,
}: {
  report: ImportReport;
  focus: RefObject<HTMLElement | null>;
  importing: boolean;
  stale: boolean;
  onImport: () => void;
  onAgain: () => void;
}) {
  const id = useId();
  const ready = importable(report);
  const flagged = report.duplicates.filter((d) => d.kind !== "already_registered");
  const skipped = report.duplicates.filter((d) => d.kind === "already_registered");

  return (
    <section ref={focus} tabIndex={-1} aria-labelledby={`${id}-title`} className="space-y-4 outline-none">
      <h2 id={`${id}-title`} className="heading-6 text-slate-900">
        Check result
      </h2>
      <Summary report={report} ready={ready} />

      <ul aria-label="The file, row by row" className={cx(STAT_STRIP, "grid-cols-2 md:grid-cols-4")}>
        <StatTile layout="segment" tone="neutral" label="Rows in the file" value={report.rows.toLocaleString("en-IN")} />
        <StatTile layout="segment" tone={ready > 0 ? "done" : "neutral"} label="Ready to import" value={ready.toLocaleString("en-IN")} hint="New patients" />
        <StatTile layout="segment" tone={report.invalid > 0 ? "danger" : "neutral"} label="Problems" value={report.invalid.toLocaleString("en-IN")} hint="Left out" />
        <StatTile layout="segment" tone="neutral" label="Already registered" value={report.already_registered.toLocaleString("en-IN")} hint="Left out" />
      </ul>

      {report.errors.length > 0 && (
        <RowTable
          caption="Rows with a problem: fix them in the spreadsheet (same row numbers) and check again"
          heading="Problem"
          rows={report.errors.map((e) => ({ key: `e${e.row}-${e.field}`, row: e.row, column: FIELD_LABEL[e.field], text: problemText(e) }))}
          truncated={report.errors_truncated ? `Only the first ${report.errors.length} problems are listed; ${plural(report.invalid, "row")} in all.` : undefined}
        />
      )}
      {flagged.length > 0 && (
        <RowTable
          caption="Will be imported, with a phone already in use"
          heading="What it means"
          rows={flagged.map((d) => ({ key: `d${d.row}`, row: d.row, text: duplicateText(d) }))}
          truncated={report.duplicates_truncated ? "More rows than are listed here share a phone." : undefined}
        />
      )}
      {skipped.length > 0 && (
        <RowTable caption="Left out as already registered" heading="Why" rows={skipped.map((d) => ({ key: `s${d.row}`, row: d.row, text: duplicateText(d) }))} />
      )}

      <div className="flex flex-wrap items-center gap-2 border-t border-line pt-4">
        <Button variant="primary" icon={<Upload className="size-4" />} loading={importing} disabled={ready === 0 || importing || stale} onClick={onImport}>
          {importing ? `Importing ${plural(ready, "patient")}…` : `Import ${plural(ready, "patient")}`}
        </Button>
        <Button variant="ghost" icon={<RotateCcw className="size-4" />} disabled={importing} onClick={onAgain}>
          Choose another file
        </Button>
        {ready > 0 && <p className="w-full text-sm text-slate-700">The file is checked again as it imports. Consent is recorded as not asked; the desk asks at each patient’s next visit.</p>}
      </div>
    </section>
  );
}

function Summary({ report, ready }: { report: ImportReport; ready: number }) {
  if (ready === 0) {
    return (
      <Alert tone="warning" role="status" title="No rows can be imported">
        {report.invalid > 0
          ? `${plural(report.invalid, "row")} ${report.invalid === 1 ? "has" : "have"} a problem${report.already_registered > 0 ? ` and ${plural(report.already_registered, "is", "are")} already registered` : ""}. Fix the rows listed below and check again.`
          : "Every row is already registered in this clinic."}
      </Alert>
    );
  }
  if (report.invalid > 0) {
    return (
      <Alert tone="warning" role="status" title={`${plural(ready, "patient")} ready, ${plural(report.invalid, "row")} with a problem`}>
        Rows with a problem are left out. Fix them and check again, or import the {plural(ready, "row")} that passed now and the rest later: rows already imported are recognised and left out.
      </Alert>
    );
  }
  return (
    <Alert tone="success" role="status" title={`${plural(ready, "patient")} ready to import`}>
      Every row passed the check{report.possible_duplicates > 0 ? `; ${plural(report.possible_duplicates, "row")} share a phone with someone and ${report.possible_duplicates === 1 ? "is" : "are"} still imported` : ""}.
    </Alert>
  );
}

function RowTable({
  caption,
  heading,
  rows,
  truncated,
}: {
  caption: string;
  heading: string;
  rows: readonly { key: string; row: number; column?: string; text: string }[];
  truncated?: string | undefined;
}) {
  const withColumn = rows.some((r) => r.column !== undefined);
  return (
    <div className="space-y-2">
      <h3 className="font-semibold text-slate-900">{caption}</h3>
      <div className={TABLE_WRAP}>
        <table role="table" className={TABLE}>
          <caption className="sr-only">{caption}</caption>
          <thead role="rowgroup">
            <tr role="row">
              <th role="columnheader" scope="col" className={cx(TH, "w-20")}>
                Row
              </th>
              {withColumn && (
                <th role="columnheader" scope="col" className={cx(TH, "w-48")}>
                  Column
                </th>
              )}
              <th role="columnheader" scope="col" className={TH}>
                {heading}
              </th>
            </tr>
          </thead>
          <tbody role="rowgroup">
            {rows.map((r) => (
              <tr key={r.key} role="row" className={TR}>
                <th role="rowheader" scope="row" className={cx(TD, "font-medium tabular-nums")}>
                  <span className="md:hidden">Row </span>
                  {r.row}
                </th>
                {withColumn && (
                  <td role="cell" data-label="Column" className={TD}>
                    {r.column}
                  </td>
                )}
                <td role="cell" data-label={heading} className={cx(TD, "text-pretty")}>
                  {r.text}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {truncated !== undefined && <p className="text-sm text-slate-700">{truncated}</p>}
    </div>
  );
}

function Done({ report, name, focus, onAgain }: { report: ImportReport; name: string; focus: RefObject<HTMLElement | null>; onAgain: () => void }) {
  const left = report.invalid + report.already_registered;
  return (
    <section ref={focus} tabIndex={-1} aria-label="Import finished" className="space-y-4 outline-none">
      <Alert
        tone={report.imported > 0 ? "success" : "warning"}
        role="status"
        title={report.imported > 0 ? `Imported ${plural(report.imported, "patient")} into ${name}` : "No patients were imported"}
        action={
          <div className="flex flex-wrap gap-2">
            <Link href="/ops" className={buttonClasses("secondary", "sm")}>
              Back to clinics
            </Link>
            <Button size="sm" variant="ghost" icon={<RotateCcw className="size-4" />} onClick={onAgain}>
              Import another file
            </Button>
          </div>
        }
      >
        {report.imported > 0 && <p>Codes {codeRange(report.codes)}. Consent is recorded as not asked; the desk asks at each patient’s next visit.</p>}
        {left > 0 && (
          <p>
            {plural(left, "row")} left out
            {report.invalid > 0 && report.already_registered > 0
              ? ` (${report.invalid} with a problem, ${report.already_registered} already registered)`
              : report.invalid > 0
                ? " with a problem"
                : " as already registered"}
            .
          </p>
        )}
      </Alert>
    </section>
  );
}

function Failure({ error, during, onRetry }: { error: unknown; during: "check" | "import"; onRetry: () => void }) {
  if (error instanceof ApiError && error.code === "REQ_REQUEST_ENTITY_TOO_LARGE") {
    return (
      <Alert tone="danger" role="alert" title="The file is over 2 MB">
        Split it into smaller files (for example by year of registration) and import each one. Nothing was imported.
      </Alert>
    );
  }
  if (error instanceof ApiError && error.code === "PAT_IMPORT_INVALID") {
    const problems = Array.isArray(error.details.problems) ? error.details.problems.filter((p): p is string => typeof p === "string") : [];
    return (
      <Alert tone="danger" role="alert" title="The file cannot be read">
        <p>Nothing was imported. Fix the file and check it again:</p>
        {problems.length > 0 && (
          <ul className="mt-1 list-disc space-y-0.5 pl-5">
            {problems.map((p) => (
              <li key={p}>{p}</li>
            ))}
          </ul>
        )}
        <p className="mt-1 text-sm text-slate-700">Ref: {error.requestId}</p>
      </Alert>
    );
  }
  return (
    <ErrorNotice
      error={error}
      {...(during === "import" ? { message: "The import did not finish, so nothing was imported. Check the file again before importing." } : {})}
      onRetry={onRetry}
    />
  );
}
