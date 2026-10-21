"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState, type FormEvent } from "react";

import { ApiError, apiGet, apiPost, type GetResponse } from "@/lib/api/client";

import { readRememberedClinic } from "./clinic-selection";
import { ErrorNotice } from "./ErrorNotice";
import { ROLE_LABELS } from "./labels";
import { TODAY_PATH, postSignInPath } from "./landing";
import {
  AUTH_INVALID_CREDENTIALS,
  AUTH_LOCKED,
  formatWait,
  isRetryable,
} from "./messages";

type Invite = GetResponse<"/api/v1/auth/invites/{token}">;

type Load =
  | { readonly status: "loading" }
  | { readonly status: "ready"; readonly invite: Invite }
  | { readonly status: "failed"; readonly error: unknown };

const MIN_LENGTH = 12;

/**
 * Accepting a staff invitation (FR-ORG-04): describe the invite, ask for a
 * password, accept, and land signed in. The page is public; the secret in the URL
 * is needed but, for an account that already exists, not enough: that person
 * enters their current password, which is checked and never changed (spec R13).
 * The 12-character minimum for a new password is only a hint, the API decides.
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
  const passwordRef = useRef<HTMLInputElement>(null);
  const existing = load.status === "ready" && load.invite.has_password;

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
    if (error === null) return;
    const wrongPassword = error instanceof ApiError && error.code === AUTH_INVALID_CREDENTIALS;
    (wrongPassword ? passwordRef.current : alertRef.current)?.focus();
  }, [error]);

  function retryLoad() {
    setLoad({ status: "loading" });
    setAttempt((n) => n + 1);
  }

  async function submit() {
    if (submittingRef.current) return;
    if (!existing && password !== confirmation) {
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
      router.replace(postSignInPath(data, readRememberedClinic(), TODAY_PATH));
    } catch (failure) {
      if (
        failure instanceof ApiError &&
        (failure.code === AUTH_INVALID_CREDENTIALS || failure.code === AUTH_LOCKED)
      ) {
        setPassword("");
      }
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
      <section className="p-6 sm:p-8">
        <p role="status">Checking your invitation…</p>
      </section>
    );
  }

  if (load.status === "failed") {
    // 404 unknown, 410 expired or already used: the API says which, in words.
    const gone = load.error instanceof ApiError && (load.error.status === 404 || load.error.status === 410);
    return (
      <section className="space-y-4 p-6 sm:p-8">
        <h1 className="text-2xl font-bold tracking-tight">Invitation</h1>
        <ErrorNotice error={load.error} {...(isRetryable(load.error) ? { onRetry: retryLoad } : {})} />
        {gone && (
          <p>
            Ask your clinic for a new invitation, or{" "}
            <Link href="/sign-in" className="text-brand-800 underline">
              sign in
            </Link>{" "}
            if you have already joined.
          </p>
        )}
      </section>
    );
  }

  const { invite } = load;
  const wrongPassword = error instanceof ApiError && error.code === AUTH_INVALID_CREDENTIALS;
  const lockedMessage =
    error instanceof ApiError && error.code === AUTH_LOCKED && error.retryAfterSeconds !== undefined
      ? `Too many attempts. Try again in ${formatWait(error.retryAfterSeconds)}.`
      : undefined;
  return (
    <section aria-labelledby="invite-heading" className="space-y-5 p-6 sm:p-8">
      <h1 id="invite-heading" className="text-2xl font-bold tracking-tight">
        Join {invite.clinic_name}
      </h1>
      <p>
        {invite.full_name}, you have been invited as <strong>{ROLE_LABELS[invite.role]}</strong>.
      </p>

      {error !== null && (
        <ErrorNotice
          id="invite-error"
          ref={alertRef}
          error={error}
          {...(lockedMessage === undefined ? {} : { message: lockedMessage })}
        />
      )}

      <form onSubmit={onSubmit} className="space-y-4">
        {invite.has_password ? (
          // An account that already exists keeps its password (spec R13): the person proves
          // it is theirs by entering it, and nothing is set or changed.
          <div className="space-y-1">
            <p id="existing-hint" className="text-sm text-slate-700">
              You already have a MediEase account, so you keep your password. Enter it to join{" "}
              {invite.clinic_name}.
            </p>
            <label htmlFor="current-password" className="block font-medium">
              Your MediEase password
            </label>
            <input
              id="current-password"
              ref={passwordRef}
              type="password"
              autoComplete="current-password"
              required
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              aria-invalid={wrongPassword ? true : undefined}
              aria-describedby={error !== null ? "invite-error" : "existing-hint"}
              className="min-h-10 w-full rounded-lg border border-slate-400 bg-white px-3 py-2 text-slate-900 placeholder:text-slate-500 hover:border-slate-500 aria-[invalid=true]:border-red-700 disabled:bg-slate-100 disabled:text-slate-600"
            />
          </div>
        ) : (
          <>
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
                className="min-h-10 w-full rounded-lg border border-slate-400 bg-white px-3 py-2 text-slate-900 placeholder:text-slate-500 hover:border-slate-500 aria-[invalid=true]:border-red-700 disabled:bg-slate-100 disabled:text-slate-600"
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
                className="min-h-10 w-full rounded-lg border border-slate-400 bg-white px-3 py-2 text-slate-900 placeholder:text-slate-500 hover:border-slate-500 aria-[invalid=true]:border-red-700 disabled:bg-slate-100 disabled:text-slate-600"
              />
              {mismatch && (
                <p id="mismatch" role="alert" className="text-sm text-red-900">
                  The two passwords are not the same.
                </p>
              )}
            </div>
          </>
        )}
        <button
          type="submit"
          disabled={submitting}
          className="w-full inline-flex min-h-10 items-center justify-center gap-2 rounded-lg bg-brand-700 px-4 py-2 font-medium text-white transition-colors hover:bg-brand-800 disabled:cursor-not-allowed disabled:bg-slate-400 motion-reduce:transition-none"
        >
          {submitting ? "Joining…" : invite.has_password ? "Join" : "Set password and join"}
        </button>
      </form>
    </section>
  );
}