"use client";

import { CircleCheck, ShieldCheck, Trash2, Upload as UploadIcon } from "lucide-react";
import { type FormEvent, useEffect, useRef, useState } from "react";

import { buttonClasses } from "@/components/ui/Button";
import { INPUT, INPUT_BASE, LABEL } from "@/components/ui/Field";
import { Spinner } from "@/components/ui/Spinner";
import { ErrorNotice } from "@/features/auth/ErrorNotice";
import { DEFAULT_ZONE } from "@/features/portal/data";
import { PortalCard, usePortal } from "@/features/portal/PortalShell";
import { ApiError } from "@/lib/api/client";
import type { components } from "@/lib/api/schema";
import { portalDelete, portalGet, portalPost, portalPostForm } from "@/lib/auth/portal-session";
import { portalDate } from "@/lib/i18n/portal";

export type Upload = components["schemas"]["PrescriptionUpload"];

const ONE = "/api/v1/portal/prescription-uploads/{upload_id}" as const;
/** While the file is checked: poll every 2 s; after a minute say it is slow (and keep polling). */
export const POLL_MS = 2_000;
const SLOW_AFTER_POLLS = 30;
const CHECKING: ReadonlySet<Upload["state"]> = new Set(["QUARANTINED", "SCANNING", "EXTRACTING"]);
/** The upload a turn can use: verified, with a version chosen. */
export function usableUpload(upload: Upload | null): string | null {
  return upload?.state === "VERIFIED" && upload.verification?.selected != null ? upload.id : null;
}

const field = `${INPUT} mt-1 min-h-11`;
const primary = `${buttonClasses("primary", "md")} min-h-11`;
const secondary = `${buttonClasses("secondary", "md")} min-h-11`;
/** The file input's own button styled as a secondary button (it stays one native control). */
const FILE =
  "block w-full cursor-pointer rounded-lg border border-dashed border-slate-400 bg-slate-50 p-2 text-sm text-slate-800 file:mr-3 file:min-h-10 file:cursor-pointer file:rounded-md file:border-0 file:bg-brand-700 file:px-4 file:font-semibold file:text-white hover:border-brand-300 hover:bg-brand-50";

/**
 * A prescription that is not in the account (M7b; FR-UPL-01..05; spec prescription-uploads §8;
 * decisions D3, D6, D7). Upload a photo or PDF, or type the printed code; follow the check while
 * the worker scans and reads it; answer the last-4 check for someone else's prescription; choose
 * the uploaded or the latest version when the upload is an older one (never chosen for the user).
 * `onChange` reports the upload so the page can name it as the turn's context once usable.
 */
export function UploadPanel({ onChange }: Readonly<{ onChange: (upload: Upload | null) => void }>) {
  const { s, leave } = usePortal();
  const u = s.assistant.upload;
  const [upload, setUpload] = useState<Upload | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [code, setCode] = useState("");
  const [digits, setDigits] = useState("");
  const [polls, setPolls] = useState(0);
  const fileInput = useRef<HTMLInputElement | null>(null);

  function show(next: Upload | null) {
    setUpload(next);
    onChange(next);
  }

  function failed(failure: unknown) {
    if (!leave(failure)) setError(failure);
  }

  const checking = upload !== null && CHECKING.has(upload.state);
  const uploadId = upload?.id;
  useEffect(() => {
    if (!checking || uploadId === undefined) return;
    const timer = setTimeout(() => {
      portalGet(ONE, { pathParams: { upload_id: uploadId } }).then(
        ({ data }) => {
          setPolls((n) => n + 1);
          show(data);
        },
        (failure: unknown) => failed(failure),
      );
    }, POLL_MS);
    return () => clearTimeout(timer);
    // eslint-disable-next-line react-hooks/exhaustive-deps -- re-armed by every new answer
  }, [checking, uploadId, upload]);

  async function run(action: () => Promise<Upload>) {
    if (busy) return;
    setBusy(true);
    setError(null);
    try {
      show(await action());
      setPolls(0);
    } catch (failure) {
      if (failure instanceof ApiError && failure.code === "UPL_CHALLENGE_FAILED" && upload !== null) {
        const left = Number(failure.details["attempts_left"] ?? 0);
        if (left === 0) {
          show((await portalGet(ONE, { pathParams: { upload_id: upload.id } })).data);
        } else {
          show({ ...upload, attempts_left: left });
        }
      } else {
        failed(failure);
      }
    } finally {
      setBusy(false);
    }
  }

  function sendFile(event: FormEvent) {
    event.preventDefault();
    const file = fileInput.current?.files?.[0];
    if (file === undefined) return;
    const form = new FormData();
    form.append("file", file);
    void run(async () => (await portalPostForm("/api/v1/portal/prescription-uploads", form, { timeoutMs: 60_000 })).data);
  }

  function sendCode(event: FormEvent) {
    event.preventDefault();
    if (code.trim() === "") {
      document.getElementById("upload-code")?.focus();
      return;
    }
    void run(async () => (await portalPost("/api/v1/portal/prescription-uploads/by-code", { code: code.trim() })).data);
  }

  function answer(event: FormEvent) {
    event.preventDefault();
    if (upload === null || !/^[0-9]{4}$/.test(digits)) return;
    const id = upload.id;
    void run(
      async () =>
        (
          await portalPost(
            "/api/v1/portal/prescription-uploads/{upload_id}/challenge",
            { phone_last4: digits },
            { pathParams: { upload_id: id } },
          )
        ).data,
    );
    setDigits("");
  }

  function choose(choice: "UPLOADED" | "LATEST") {
    if (upload === null) return;
    const id = upload.id;
    void run(
      async () =>
        (
          await portalPost(
            "/api/v1/portal/prescription-uploads/{upload_id}/selection",
            { choice },
            { pathParams: { upload_id: id } },
          )
        ).data,
    );
  }

  async function remove() {
    if (upload === null || busy) return;
    setBusy(true);
    setError(null);
    try {
      await portalDelete(ONE, { pathParams: { upload_id: upload.id } });
      show(null);
      setCode("");
      if (fileInput.current !== null) fileInput.current.value = "";
    } catch (failure) {
      failed(failure);
    } finally {
      setBusy(false);
    }
  }

  const v = upload?.verification ?? null;
  const day = (iso: string) => portalDate(iso, DEFAULT_ZONE, s);

  return (
    <PortalCard id="assistant-upload" title={u.title} icon={<UploadIcon />}>
      <p className="text-slate-800">{u.intro}</p>
      <p className="flex items-start gap-2 text-sm text-slate-700">
        <ShieldCheck aria-hidden="true" className="mt-0.5 size-4 shrink-0 text-brand-700" />
        <span>{u.privacy}</span>
      </p>

      {(upload === null || upload.state === "REJECTED") && (
        <>
          {upload?.state === "REJECTED" && (
            <div role="status" className="rounded-lg border border-warning-line bg-warning-soft p-3 text-slate-900">
              <p className="font-medium">{u.rejected[upload.rejection_code ?? ""] ?? u.rejectedOther}</p>
              {upload.rejection_code !== "UPL_WITHDRAWN" && <p className="text-sm">{u.tryAgain}</p>}
            </div>
          )}
          <form onSubmit={sendFile} className="space-y-2 rounded-lg border border-line p-3">
            <label htmlFor="upload-file" className={LABEL}>
              {u.file}
            </label>
            <input
              id="upload-file"
              ref={fileInput}
              type="file"
              accept="application/pdf,image/jpeg,image/png"
              aria-describedby="upload-file-help"
              className={`${FILE} mt-1`}
            />
            <p id="upload-file-help" className="text-sm text-slate-700">
              {u.fileHelp}
            </p>
            <button type="submit" disabled={busy} className={primary}>
              {busy ? u.sending : u.send}
            </button>
          </form>
          <p className="flex items-center gap-3 text-sm font-semibold uppercase tracking-wide text-slate-600 before:h-px before:flex-1 before:bg-line after:h-px after:flex-1 after:bg-line">
            {u.or}
          </p>
          <form onSubmit={sendCode} className="space-y-2 rounded-lg border border-line p-3">
            <label htmlFor="upload-code" className={LABEL}>
              {u.code}
            </label>
            <input
              id="upload-code"
              value={code}
              onChange={(event) => setCode(event.target.value)}
              maxLength={80}
              autoComplete="off"
              spellCheck={false}
              aria-describedby="upload-code-help"
              className={`${field} font-mono`}
            />
            <p id="upload-code-help" className="break-words text-sm text-slate-700">
              {u.codeHelp}
            </p>
            <button type="submit" disabled={busy} className={secondary}>
              {u.verify}
            </button>
          </form>
        </>
      )}

      {checking && (
        <div role="status" aria-busy="true" className="flex items-start gap-3 rounded-lg border border-info-line bg-info-soft p-3 text-slate-900">
          <Spinner />
          <div>
            <p>{u.checking}</p>
            {polls >= SLOW_AFTER_POLLS && <p className="text-sm">{u.slow}</p>}
          </div>
        </div>
      )}

      {upload?.state === "NEEDS_CHALLENGE" && (
        <form onSubmit={answer} className="space-y-2 rounded-lg border border-line p-3" aria-labelledby="upload-challenge-title">
          <h3 id="upload-challenge-title" className="font-semibold">
            {u.challengeTitle}
          </h3>
          <p>{u.challengeHelp}</p>
          <label htmlFor="upload-last4" className={LABEL}>
            {u.last4}
          </label>
          <input
            id="upload-last4"
            value={digits}
            onChange={(event) => setDigits(event.target.value.replace(/\D/g, "").slice(0, 4))}
            inputMode="numeric"
            autoComplete="off"
            maxLength={4}
            className={`${INPUT_BASE} mt-1 min-h-12 w-36 text-center font-mono text-xl tracking-[0.3em]`}
          />
          {upload.attempts_left !== null && upload.attempts_left < 5 && (
            <p role="status" className="text-sm font-medium text-danger">
              {u.attemptsLeft(upload.attempts_left)}
            </p>
          )}
          <button type="submit" disabled={busy || digits.length !== 4} className={primary}>
            {u.check}
          </button>
        </form>
      )}

      {upload?.state === "VERIFIED" && v !== null && (
        <div className="space-y-2 rounded-lg border border-success-line bg-success-soft p-3 text-slate-900">
          <p className="flex items-start gap-2 font-medium">
            <CircleCheck aria-hidden="true" className="mt-0.5 size-4 shrink-0 text-success" />
            <span>{u.verified(v.doctor_name, v.clinic_name, day(v.issued_at), v.version)}</span>
          </p>
          {v.access === "REPRESENTATIVE" && <p>{u.representative(day(v.expires_at))}</p>}
          {v.superseded && v.latest_version !== null && (
            <fieldset className="space-y-2">
              <legend className="font-medium">
                {u.historical(v.version, v.latest_version, v.latest_issued_at === null ? "" : day(v.latest_issued_at))}
              </legend>
              <div className="flex flex-wrap gap-2">
                <button
                  type="button"
                  aria-pressed={v.selected === "UPLOADED"}
                  disabled={busy}
                  onClick={() => choose("UPLOADED")}
                  className={v.selected === "UPLOADED" ? primary : secondary}
                >
                  {u.useUploaded(v.version)}
                </button>
                <button
                  type="button"
                  aria-pressed={v.selected === "LATEST"}
                  disabled={busy}
                  onClick={() => choose("LATEST")}
                  className={v.selected === "LATEST" ? primary : secondary}
                >
                  {u.useLatest(v.latest_version)}
                </button>
              </div>
            </fieldset>
          )}
          {v.selected !== null && (
            <p role="status" className="font-semibold">
              {u.using(v.selected === "LATEST" && v.latest_version !== null ? v.latest_version : v.version)}
            </p>
          )}
        </div>
      )}

      {error !== null && <ErrorNotice error={error} />}

      {upload !== null && upload.state !== "REJECTED" && (
        <button type="button" disabled={busy} onClick={() => void remove()} className={`${secondary} text-danger hover:border-danger-line hover:bg-danger-soft hover:text-danger`}>
          <Trash2 aria-hidden="true" className="size-4" />
          {u.remove}
        </button>
      )}
    </PortalCard>
  );
}
