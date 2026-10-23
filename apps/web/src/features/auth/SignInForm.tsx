"use client";

import { useRouter } from "next/navigation";
import { useEffect, useRef, useState, type FormEvent } from "react";

import { ApiError, apiPost } from "@/lib/api/client";

import { readRememberedClinic } from "./clinic-selection";
import { ErrorNotice } from "./ErrorNotice";
import { GoogleButton } from "./GoogleButton";
import { postSignInPath } from "./landing";
import {
  AUTH_INVALID_CREDENTIALS,
  AUTH_LOCKED,
  SIGN_IN_REASONS,
  formatWait,
  isRetryable,
  type SignInReason,
} from "./messages";

const ERROR_ID = "sign-in-error";

/**
 * FR-AUTH-01 / FR-AUTH-04 in the browser. One identifier field (email or phone;
 * the API normalises it) and a password. The API's error text is shown as is
 * with its Ref; a lock also says how long to wait and disables the button until
 * then. `next` has already passed `safeNextPath` on the server.
 */
export function SignInForm({ next, reason }: { next: string; reason?: SignInReason }) {
  const router = useRouter();
  const [identifier, setIdentifier] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [waitSeconds, setWaitSeconds] = useState(0);

  const submittingRef = useRef(false);
  const passwordRef = useRef<HTMLInputElement>(null);
  const alertRef = useRef<HTMLDivElement>(null);

  // Count a lock down. State changes only inside the timer callback.
  const locked = waitSeconds > 0;
  useEffect(() => {
    if (!locked) return;
    const timer = setInterval(() => setWaitSeconds((s) => Math.max(0, s - 1)), 1000);
    return () => clearInterval(timer);
  }, [locked]);

  // Move focus to what the person must look at: the password after a wrong
  // one (the alert is its description), the alert for anything else.
  useEffect(() => {
    if (error === null) return;
    const wrongPassword = error instanceof ApiError && error.code === AUTH_INVALID_CREDENTIALS;
    (wrongPassword ? passwordRef.current : alertRef.current)?.focus();
  }, [error]);

  async function submit() {
    if (submittingRef.current || locked) return;
    submittingRef.current = true;
    setSubmitting(true);
    setError(null);
    try {
      const { data } = await apiPost("/api/v1/auth/sign-in", {
        identifier: identifier.trim(),
        password,
      });
      // Stay in the "signing in" state: the page is about to change.
      router.replace(postSignInPath(data, readRememberedClinic(), next));
    } catch (failure) {
      if (failure instanceof ApiError && failure.code === AUTH_LOCKED) {
        setWaitSeconds(failure.retryAfterSeconds ?? 0);
      }
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

  const lockedMessage =
    locked && error instanceof ApiError && error.code === AUTH_LOCKED
      ? `Too many attempts. Try again in ${formatWait(waitSeconds)}.`
      : undefined;
  const invalid = error instanceof ApiError && error.code === AUTH_INVALID_CREDENTIALS;

  return (
    <section aria-labelledby="sign-in-heading" className="space-y-5 p-6 sm:p-8">
      <h1 id="sign-in-heading" className="text-2xl font-bold tracking-tight">
        Sign in to MediEase
      </h1>

      {reason !== undefined && error === null && (
        <p role="status" className="rounded-lg border border-slate-300 bg-slate-50 p-3">
          {SIGN_IN_REASONS[reason]}
        </p>
      )}

      {error !== null && (
        <ErrorNotice
          id={ERROR_ID}
          ref={alertRef}
          error={error}
          {...(lockedMessage === undefined ? {} : { message: lockedMessage })}
          {...(isRetryable(error) ? { onRetry: () => void submit() } : {})}
        />
      )}

      <form onSubmit={onSubmit} className="space-y-4">
        <div className="space-y-1">
          <label htmlFor="identifier" className="block font-medium">
            Email or phone number
          </label>
          <input
            id="identifier"
            name="identifier"
            type="text"
            autoComplete="username"
            autoCapitalize="none"
            spellCheck={false}
            required
            value={identifier}
            onChange={(event) => setIdentifier(event.target.value)}
            aria-describedby={error !== null ? ERROR_ID : undefined}
            className="min-h-10 w-full rounded-lg border border-slate-400 bg-white px-3 py-2 text-slate-900 placeholder:text-slate-500 hover:border-slate-500 aria-[invalid=true]:border-red-700 disabled:bg-slate-100 disabled:text-slate-600"
          />
        </div>

        <div className="space-y-1">
          <label htmlFor="password" className="block font-medium">
            Password
          </label>
          <div className="flex gap-2">
            <input
              id="password"
              name="password"
              ref={passwordRef}
              type={showPassword ? "text" : "password"}
              autoComplete="current-password"
              required
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              aria-invalid={invalid ? true : undefined}
              aria-describedby={error !== null ? ERROR_ID : undefined}
              className="min-h-10 w-full rounded-lg border border-slate-400 bg-white px-3 py-2 text-slate-900 placeholder:text-slate-500 hover:border-slate-500 aria-[invalid=true]:border-red-700 disabled:bg-slate-100 disabled:text-slate-600"
            />
            <button
              type="button"
              aria-pressed={showPassword}
              onClick={() => setShowPassword((shown) => !shown)}
              className="shrink-0 whitespace-nowrap rounded-lg border border-slate-400 px-3 py-2"
            >
              {showPassword ? "Hide password" : "Show password"}
            </button>
          </div>
        </div>

        <button
          type="submit"
          disabled={submitting || locked}
          className="w-full inline-flex min-h-10 items-center justify-center gap-2 rounded-lg bg-brand-700 px-4 py-2 font-medium text-white transition-colors hover:bg-brand-800 disabled:cursor-not-allowed disabled:bg-slate-400 motion-reduce:transition-none"
        >
          {submitting ? "Signing in…" : "Sign in"}
        </button>
      </form>

      <GoogleButton intent="staff" next={next} email={identifier} />
    </section>
  );
}
