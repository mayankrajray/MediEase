"use client";

import { type FormEvent, useEffect, useRef, useState } from "react";

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

const field = "block min-h-11 w-full rounded-lg border border-slate-300 bg-white p-2";
const primary =
  "inline-flex min-h-11 items-center rounded-lg bg-brand-700 px-4 font-semibold text-white hover:bg-brand-800 disabled:opacity-60";
const secondary = "inline-flex min-h-11 items-center rounded-lg border border-slate-300 px-4 font-medium disabled:opacity-60";

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
    if (code.trim() === "") return;
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
    <PortalCard id="assistant-upload" title={u.title}>
      <p>{u.intro}</p>
      <p className="text-sm text-slate-700">{u.privacy}</p>

      {(upload === null || upload.state === "REJECTED") && (
        <>
          {upload?.state === "REJECTED" && (
            <div role="status" className="rounded-lg border border-amber-500 bg-amber-50 p-3">
              <p className="font-medium">{u.rejected[upload.rejection_code ?? ""] ?? u.rejectedOther}</p>
              {upload.rejection_code !== "UPL_WITHDRAWN" && <p className="text-sm">{u.tryAgain}</p>}
            </div>
          )}
          <form onSubmit={sendFile} className="space-y-2">
            <label htmlFor="upload-file" className="block font-medium">
              {u.file}
            </label>
            <input
              id="upload-file"
              ref={fileInput}
              type="file"
              accept="application/pdf,image/jpeg,image/png"
              aria-describedby="upload-file-help"
              className={field}
            />
            <p id="upload-file-help" className="text-sm text-slate-700">
              {u.fileHelp}
            </p>
            <button type="submit" disabled={busy} className={primary}>
              {busy ? u.sending : u.send}
            </button>
          </form>
          <p className="font-medium">{u.or}</p>
          <form onSubmit={sendCode} className="space-y-2">
            <label htmlFor="upload-code" className="block font-medium">
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
            <button type="submit" disabled={busy || code.trim() === ""} className={secondary}>
              {u.verify}
            </button>
          </form>
        </>
      )}

      {checking && (
        <div role="status" aria-busy="true" className="rounded-lg border border-slate-200 p-3">
          <p>{u.checking}</p>
          {polls >= SLOW_AFTER_POLLS && <p className="text-sm">{u.slow}</p>}
        </div>
      )}

      {upload?.state === "NEEDS_CHALLENGE" && (
        <form onSubmit={answer} className="space-y-2" aria-labelledby="upload-challenge-title">
          <h3 id="upload-challenge-title" className="font-semibold">
            {u.challengeTitle}
          </h3>
          <p>{u.challengeHelp}</p>
          <label htmlFor="upload-last4" className="block font-medium">
            {u.last4}
          </label>
          <input
            id="upload-last4"
            value={digits}
            onChange={(event) => setDigits(event.target.value.replace(/\D/g, "").slice(0, 4))}
            inputMode="numeric"
            autoComplete="off"
            maxLength={4}
            className={`${field} max-w-32 font-mono`}
          />
          {upload.attempts_left !== null && upload.attempts_left < 5 && (
            <p role="status">{u.attemptsLeft(upload.attempts_left)}</p>
          )}
          <button type="submit" disabled={busy || digits.length !== 4} className={primary}>
            {u.check}
          </button>
        </form>
      )}

      {upload?.state === "VERIFIED" && v !== null && (
        <div className="space-y-2 rounded-lg border border-brand-700 p-3">
          <p className="font-medium">{u.verified(v.doctor_name, v.clinic_name, day(v.issued_at), v.version)}</p>
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
            <p role="status">
              {u.using(v.selected === "LATEST" && v.latest_version !== null ? v.latest_version : v.version)}
            </p>
          )}
        </div>
      )}

      {error !== null && <ErrorNotice error={error} />}

      {upload !== null && upload.state !== "REJECTED" && (
        <button type="button" disabled={busy} onClick={() => void remove()} className={secondary}>
          {u.remove}
        </button>
      )}
    </PortalCard>
  );
}
