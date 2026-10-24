"use client";

import QRCode from "qrcode";
import { useEffect, useRef, useState } from "react";

import { ErrorNotice } from "@/features/auth/ErrorNotice";
import { useSession } from "@/features/auth/SessionProvider";
import { useClinic } from "@/features/shell/ClinicGate";
import { formatDateTime } from "@/lib/format/time";

import { usePatientApi, type PortalInvitation, type PortalStatus } from "./api";
import type { Patient } from "./fields";

const METHOD_LABELS: Readonly<Record<string, string>> = {
  INVITE: "by invite",
  RX_LINK: "from a prescription link",
};

const SMALL_BUTTON =
  "inline-flex min-h-8 items-center justify-center gap-2 rounded-lg border border-slate-400 bg-white px-3 py-1 text-sm font-medium text-slate-900 transition-colors hover:bg-slate-100 disabled:cursor-not-allowed disabled:text-slate-500 motion-reduce:transition-none";

/**
 * The *Patient app* card (M6b-P1 decision 8A, spec R1, R8, R14): whether this record is linked to
 * a patient's MediEase account, an invite shown once with its QR code, and unlinking. Staff never
 * see the account's email or name. The invite's URL lives in this component's state only.
 */
export function PatientPortalCard({ patient }: Readonly<{ patient: Patient }>) {
  const api = usePatientApi();
  const clinic = useClinic();
  const { endSession } = useSession();
  const [status, setStatus] = useState<PortalStatus | undefined>(undefined);
  const [invitation, setInvitation] = useState<PortalInvitation | undefined>(
    undefined,
  );
  // The QR code of one invitation's URL; a newer invitation draws its own.
  const [qr, setQr] = useState<{ readonly url: string; readonly data: string } | undefined>(undefined);
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  const [confirming, setConfirming] = useState(false);
  const [copied, setCopied] = useState("");
  const field = useRef<HTMLInputElement>(null);

  useEffect(() => {
    let cancelled = false;
    api.portalStatus(patient.id).then(
      (next) => {
        if (!cancelled) setStatus(next);
      },
      (failure: unknown) => {
        if (!cancelled && !endSession(failure)) setError(failure);
      },
    );
    return () => {
      cancelled = true;
    };
  }, [api, patient.id, endSession]);

  useEffect(() => {
    if (invitation === undefined) return;
    let cancelled = false;
    const { url } = invitation;
    void QRCode.toDataURL(url, { margin: 1, width: 192, errorCorrectionLevel: "M" }).then((data) => {
      if (!cancelled) setQr({ url, data });
    });
    return () => {
      cancelled = true;
    };
  }, [invitation]);

  async function run<T>(call: () => Promise<T>, done: (value: T) => void) {
    if (busy) return;
    setBusy(true);
    setError(null);
    try {
      done(await call());
    } catch (failure) {
      if (!endSession(failure)) setError(failure);
    } finally {
      setBusy(false);
    }
  }

  function invite() {
    void run(
      () => api.invitePortal(patient.id),
      (created) => {
        setInvitation(created);
        setCopied("");
        setStatus({
          status: "INVITED",
          method: null,
          linked_at: null,
          invite_expires_at: created.expires_at,
        });
      },
    );
  }

  function unlink() {
    void run(
      () => api.unlinkPortal(patient.id),
      (next) => {
        setStatus(next);
        setConfirming(false);
      },
    );
  }

  async function copy(url: string) {
    try {
      await navigator.clipboard.writeText(url);
      setCopied("Link copied.");
    } catch {
      field.current?.select();
      setCopied(
        "Could not copy automatically. The link is selected: press Ctrl+C.",
      );
    }
  }

  return (
    <section
      aria-labelledby="portal-heading"
      className="space-y-3 rounded-card border border-slate-200 bg-white p-4 shadow-card"
    >
      <h2 id="portal-heading" className="text-lg font-bold">
        Patient app
      </h2>
      {error !== null && <ErrorNotice error={error} />}
      {status === undefined && error === null && (
        <p role="status">Checking the patient app…</p>
      )}

      {status?.status === "NOT_LINKED" && (
        <>
          <p>
            Not linked. Invite {patient.full_name} to see their appointments and
            prescriptions in the MediEase app.
          </p>
          <button
            type="button"
            onClick={invite}
            disabled={busy}
            className={SMALL_BUTTON}
          >
            Invite to the patient app
          </button>
        </>
      )}

      {status?.status === "INVITED" && (
        <>
          <p>
            Invited, link expires{" "}
            {status.invite_expires_at !== null &&
              formatDateTime(status.invite_expires_at, clinic.timezone)}
            .
          </p>
          <button
            type="button"
            onClick={invite}
            disabled={busy}
            className={SMALL_BUTTON}
          >
            Invite again
          </button>
        </>
      )}

      {status?.status === "LINKED" && (
        <>
          <p>
            Linked {status.method !== null ? METHOD_LABELS[status.method] : ""}{" "}
            since{" "}
            {status.linked_at !== null &&
              formatDateTime(status.linked_at, clinic.timezone)}
            .
          </p>
          {confirming ? (
            <div className="space-y-2 rounded-lg border border-red-800 bg-red-50 p-3">
              <p className="font-medium">
                Unlink? The patient will no longer see this clinic&apos;s
                appointments and prescriptions in the app. The record itself is
                not changed.
              </p>
              <div className="flex gap-2">
                <button
                  type="button"
                  onClick={unlink}
                  disabled={busy}
                  className="rounded px-4 py-2 font-semibold bg-red-700 text-white hover:bg-red-800"
                >
                  Yes, unlink
                </button>
                <button
                  type="button"
                  onClick={() => setConfirming(false)}
                  className={SMALL_BUTTON}
                >
                  Cancel
                </button>
              </div>
            </div>
          ) : (
            <button
              type="button"
              onClick={() => setConfirming(true)}
              className="rounded-lg border border-red-800 px-4 py-2 font-medium text-red-900 hover:bg-red-50"
            >
              Unlink
            </button>
          )}
        </>
      )}

      {invitation !== undefined && status?.status === "INVITED" && (
        <div className="flex flex-wrap items-start gap-4 rounded-lg border border-slate-400 bg-slate-50 p-4">
          {qr?.url === invitation.url && (
            // A data: URL made here; next/image has nothing to optimise.
            // eslint-disable-next-line @next/next/no-img-element
            <img
              src={qr.data}
              width={192}
              height={192}
              alt="QR code of the patient app invitation"
              className="rounded-card border border-slate-200 bg-white"
            />
          )}
          <div className="min-w-0 flex-1 space-y-2">
            <label htmlFor="portal-invite-link" className="block font-medium">
              Invitation link for {patient.full_name}
            </label>
            <div className="flex gap-2">
              <input
                id="portal-invite-link"
                ref={field}
                readOnly
                value={invitation.url}
                onFocus={(e) => e.target.select()}
                data-testid="portal-invite-link"
                className="w-full rounded-lg border border-slate-400 bg-white px-3 py-2 font-mono text-sm"
              />
              <button
                type="button"
                onClick={() => void copy(invitation.url)}
                className={SMALL_BUTTON}
              >
                Copy link
              </button>
            </div>
            <p role="status" className="min-h-6 text-sm">
              {copied}
            </p>
            <p className="text-sm text-slate-800">
              This link is shown <strong>only now</strong>. The patient scans
              the code or opens the link, signs in to MediEase and confirms. It
              works once and is valid for 7 days; inviting again replaces it.
            </p>
          </div>
        </div>
      )}
    </section>
  );
}
