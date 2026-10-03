"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState, type FormEvent } from "react";

import { ApiError, apiGet, apiPost, type GetResponse } from "@/lib/api/client";

import { readRememberedClinic } from "./clinic-selection";
import { ErrorNotice } from "./ErrorNotice";
import { ROLE_LABELS } from "./labels";
import { QUEUE_PATH, postSignInPath } from "./landing";
import { isRetryable } from "./messages";

type Invite = GetResponse<"/api/v1/auth/invites/{token}">;

type Load =
  | { readonly status: "loading" }
  | { readonly status: "ready"; readonly invite: Invite }
  | { readonly status: "failed"; readonly error: unknown };

const MIN_LENGTH = 12;

/**
 * Accepting a staff invitation (FR-ORG-04): describe the invite, ask for a
 * password, accept, and land signed in. The page is public; the secret in the URL
 * is the authority. The 12-character minimum is only a hint, the API decides.
 */
export function AcceptInviteForm({ token }: { token: string }) {
  const router = useRouter();
  const [load, setLoad] = useState<Load>({ status: "loading" });
  const [attempt, setAttempt] = useState(0);
  const [password, setPassword] = useState("");
  const [confirmation, setConfirmation] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [mismatch, setMismatch] = useState(false);
  const submittingRef = useRef(false);
  const alertRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    let cancelled = false;
    apiGet("/api/v1/auth/invites/{token}", { pathParams: { token } }).then(
      ({ data }) => {
        if (!cancelled) setLoad({ status: "ready", invite: data });
      },
      (failure: unknown) => {
        if (!cancelled) setLoad({ status: "failed", error: failure });
      },
    );
    return () => {
      cancelled = true;
    };
  }, [token, attempt]);

  useEffect(() => {
    if (error !== null) alertRef.current?.focus();
  }, [error]);

  function retryLoad() {
    setLoad({ status: "loading" });
    setAttempt((n) => n + 1);
  }

  async function submit() {
    if (submittingRef.current) return;
    if (password !== confirmation) {
      setMismatch(true);
      return;
    }
    setMismatch(false);
    submittingRef.current = true;
    setSubmitting(true);
    setError(null);
    try {
      const { data } = await apiPost(
        "/api/v1/auth/invites/{token}/accept",
        { password },
        { pathParams: { token } },
      );
      router.replace(postSignInPath(data, readRememberedClinic(), QUEUE_PATH));
    } catch (failure) {
      setError(failure);
      submittingRef.current = false;
      setSubmitting(false);
    }
  }

  function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    void submit();
  }

  if (load.status === "loading") {
    return (
      <section className="mx-auto w-full max-w-sm p-6">
        <p role="status">Checking your invitation…</p>
      </section>
    );
  }

  if (load.status === "failed") {
    // 404 unknown, 410 expired or already used: the API says which, in words.
    const gone = load.error instanceof ApiError && (load.error.status === 404 || load.error.status === 410);
    return (
      <section className="mx-auto w-full max-w-sm space-y-4 p-6">
        <h1 className="text-2xl font-bold">Invitation</h1>
        <ErrorNotice error={load.error} {...(isRetryable(load.error) ? { onRetry: retryLoad } : {})} />
        {gone && (
          <p>
            Ask your clinic for a new invitation, or{" "}
            <Link href="/sign-in" className="text-blue-800 underline">
              sign in
            </Link>{" "}
            if you have already joined.
          </p>
        )}
      </section>
    );
  }

  const { invite } = load;
  return (
    <section aria-labelledby="invite-heading" className="mx-auto w-full max-w-sm space-y-5 p-6">
      <h1 id="invite-heading" className="text-2xl font-bold">
        Join {invite.clinic_name}
      </h1>
      <p>
        {invite.full_name}, you have been invited as <strong>{ROLE_LABELS[invite.role]}</strong>.
      </p>

      {invite.has_password ? (
        // Accepting sets the account's password, which must never overwrite an existing
        // account's (M1-P6 design, known issue): existing accounts sign in instead.
        <div className="space-y-3 rounded border border-slate-400 bg-slate-50 p-4">
          <p>
            This invitation is for a MediEase account that already exists. Sign in with that account. If{" "}
            {invite.clinic_name} does not appear afterwards, contact MediEase support.
          </p>
          <Link
            href="/sign-in"
            className="inline-block rounded bg-blue-800 px-4 py-2 font-semibold text-white hover:bg-blue-900"
          >
            Go to sign in
          </Link>
        </div>
      ) : (
        <>
          {error !== null && <ErrorNotice id="invite-error" ref={alertRef} error={error} />}
          <form onSubmit={onSubmit} className="space-y-4">
            <div className="space-y-1">
              <label htmlFor="new-password" className="block font-medium">
                Choose a password
              </label>
              <input
                id="new-password"
                type="password"
                autoComplete="new-password"
                required
                minLength={MIN_LENGTH}
                value={password}
                onChange={(event) => setPassword(event.target.value)}
                aria-describedby="password-hint"
                className="w-full rounded border border-slate-500 px-3 py-2"
              />
              <p id="password-hint" className="text-sm text-slate-700">
                At least {MIN_LENGTH} characters.
              </p>
            </div>
            <div className="space-y-1">
              <label htmlFor="confirm-password" className="block font-medium">
                Type it again
              </label>
              <input
                id="confirm-password"
                type="password"
                autoComplete="new-password"
                required
                value={confirmation}
                onChange={(event) => {
                  setConfirmation(event.target.value);
                  setMismatch(false);
                }}
                aria-invalid={mismatch ? true : undefined}
                aria-describedby={mismatch ? "mismatch" : undefined}
                className="w-full rounded border border-slate-500 px-3 py-2"
              />
              {mismatch && (
                <p id="mismatch" role="alert" className="text-sm text-red-900">
                  The two passwords are not the same.
                </p>
              )}
            </div>
            <button
              type="submit"
              disabled={submitting}
              className="w-full rounded bg-blue-800 px-4 py-2 font-semibold text-white hover:bg-blue-900 disabled:cursor-not-allowed disabled:bg-slate-500"
            >
              {submitting ? "Joining…" : "Set password and join"}
            </button>
          </form>
        </>
      )}
    </section>
  );
}
