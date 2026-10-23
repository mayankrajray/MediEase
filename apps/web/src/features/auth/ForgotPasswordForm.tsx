"use client";

import Link from "next/link";
import { useEffect, useRef, useState, type FormEvent } from "react";

import { Button } from "@/components/ui/Button";
import { TextField } from "@/components/ui/Field";
import { apiPost } from "@/lib/api/client";

import { ErrorNotice } from "./ErrorNotice";
import { isRetryable } from "./messages";

export type AccountKind = "staff" | "patient";

const REQUEST_PATH = {
  staff: "/api/v1/auth/password-reset",
  patient: "/api/v1/portal/auth/password-reset",
} as const;

/**
 * "Forgot password?" (M6a-P4, FR-AUTH-05, ADR-0016 decision 7). The API answers the same way
 * whether or not the address has an account, so this page says the same thing either way.
 */
export function ForgotPasswordForm({ kind, signInHref }: { kind: AccountKind; signInHref: string }) {
  const [email, setEmail] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [sent, setSent] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const alertRef = useRef<HTMLDivElement>(null);
  const doneRef = useRef<HTMLParagraphElement>(null);

  useEffect(() => {
    if (error !== null) alertRef.current?.focus();
  }, [error]);
  useEffect(() => {
    if (sent) doneRef.current?.focus();
  }, [sent]);

  async function submit() {
    if (submitting) return;
    setSubmitting(true);
    setError(null);
    try {
      await apiPost(REQUEST_PATH[kind], { email: email.trim() });
      setSent(true);
    } catch (failure) {
      setError(failure);
    } finally {
      setSubmitting(false);
    }
  }

  function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    void submit();
  }

  return (
    <section aria-labelledby="forgot-heading" className="space-y-5 p-6 sm:p-8">
      <h1 id="forgot-heading" className="text-2xl font-bold tracking-tight">
        Reset your password
      </h1>
      {sent ? (
        <p ref={doneRef} tabIndex={-1} role="status" className="rounded-lg border border-slate-300 bg-slate-50 p-3">
          If an account uses that email, we have sent it a link to choose a new password. The link
          works once and lasts 30 minutes. Check your spam folder if it does not arrive.
        </p>
      ) : (
        <>
          <p className="text-slate-700">Enter the email you sign in with and we will send you a link.</p>
          {error !== null && (
            <ErrorNotice
              id="forgot-error"
              ref={alertRef}
              error={error}
              {...(isRetryable(error) ? { onRetry: () => void submit() } : {})}
            />
          )}
          <form onSubmit={onSubmit} className="space-y-4">
            <TextField
              id="forgot-email"
              label="Email"
              type="email"
              inputMode="email"
              autoComplete="email"
              required
              value={email}
              onChange={setEmail}
            />
            <Button type="submit" variant="primary" className="w-full" disabled={submitting}>
              {submitting ? "Sending…" : "Send the link"}
            </Button>
          </form>
        </>
      )}
      <p className="text-sm text-slate-700">
        <Link href={signInHref} className="font-medium text-brand-800 underline">
          Back to sign in
        </Link>
      </p>
    </section>
  );
}
