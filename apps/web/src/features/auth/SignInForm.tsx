"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState, type FormEvent } from "react";

import { Button } from "@/components/ui/Button";
import { PasswordField, TextField } from "@/components/ui/Field";
import { ApiError, apiPost } from "@/lib/api/client";
import { FORM_EN } from "@/lib/i18n/portal";

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
 * Staff sign-in by email or phone (M1-P6, FR-AUTH-01): a lock counts down, a wrong password keeps
 * the identifier and focuses the password, the reason a session ended is said once.
 *
 * M7c-P7 (M2; DESIGN.md §8a): both fields are checked when submitted empty and when the person
 * leaves them, with the reason under the field; the button shows that it is working; while
 * locked it is disabled and described by the message that says how long to wait. Labels keep
 * their words; on a two-field sign-in every field is required, so "(required)" is left out.
 */
export function SignInForm({ next, reason }: { next: string; reason?: SignInReason }) {
  const router = useRouter();
  const [identifier, setIdentifier] = useState("");
  const [password, setPassword] = useState("");
  const [touched, setTouched] = useState({ identifier: false, password: false });
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [waitSeconds, setWaitSeconds] = useState(0);

  const submittingRef = useRef(false);
  const identifierRef = useRef<HTMLInputElement>(null);
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

  const identifierMissing = identifier.trim() === "";
  const passwordMissing = password === "";

  async function submit() {
    if (submittingRef.current || locked) return;
    if (identifierMissing || passwordMissing) {
      setTouched({ identifier: true, password: true });
      (identifierMissing ? identifierRef : passwordRef).current?.focus();
      return;
    }
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
        setTouched((t) => ({ ...t, password: false }));
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
  const errorId = error !== null ? ERROR_ID : undefined;

  return (
    <section aria-labelledby="sign-in-heading" className="space-y-6 p-6 sm:p-8">
      <div className="space-y-1">
        <h1 id="sign-in-heading" className="heading-5">
          Sign in to MediEase
        </h1>
        <p className="text-sm text-slate-700">For clinic staff. Patients sign in to the patient app.</p>
      </div>

      {reason !== undefined && error === null && (
        <p role="status" className="rounded-xl border border-info-line bg-info-soft p-4 text-pretty text-slate-900">
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

      <form onSubmit={onSubmit} className="space-y-5" noValidate>
        <TextField
          id="identifier"
          label="Email or phone number"
          required
          requiredMark={false}
          autoComplete="username"
          autoCapitalize="none"
          spellCheck={false}
          value={identifier}
          onChange={setIdentifier}
          onBlur={() => setTouched((t) => ({ ...t, identifier: t.identifier || identifier !== "" }))}
          error={touched.identifier && identifierMissing ? FORM_EN.identifierMissing : undefined}
          describedBy={errorId}
          inputRef={identifierRef}
        />

        <PasswordField
          id="password"
          label="Password"
          required
          requiredMark={false}
          autoComplete="current-password"
          value={password}
          onChange={setPassword}
          error={touched.password && passwordMissing && !invalid ? FORM_EN.passwordMissing : undefined}
          invalid={invalid}
          describedBy={errorId}
          inputRef={passwordRef}
        />

        <Button
          type="submit"
          variant="primary"
          size="lg"
          className="w-full"
          loading={submitting}
          disabled={locked}
          aria-describedby={locked ? ERROR_ID : undefined}
        >
          {submitting ? "Signing in…" : "Sign in"}
        </Button>
      </form>

      <GoogleButton intent="staff" next={next} email={identifier} />

      <p className="text-center text-sm text-slate-700">
        <Link href="/forgot-password" className="font-semibold text-brand-800 underline underline-offset-2">
          Forgot password?
        </Link>
      </p>
    </section>
  );
}
