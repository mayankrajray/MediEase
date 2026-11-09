"use client";

import { CircleCheck } from "lucide-react";
import Link from "next/link";
import { useEffect, useRef, useState, type FormEvent } from "react";

import { Button } from "@/components/ui/Button";
import { looksLikeEmail, TextField } from "@/components/ui/Field";
import { apiPost } from "@/lib/api/client";
import { FORGOT_EN, FORM_EN, type ForgotWords, type FormWords } from "@/lib/i18n/portal";

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
 *
 * M7c-P7 (M2): the address is checked when the person leaves the field and before sending (missing
 * or not shaped like an email), with the reason under the field; the confirmation is a success
 * message that keeps the way back to sign-in.
 */
export function ForgotPasswordForm({
  kind,
  signInHref,
  words = FORGOT_EN,
  form = FORM_EN,
}: {
  kind: AccountKind;
  signInHref: string;
  /** The patient pages pass Hindi when the portal's language is Hindi (M6b-P2); staff keep English. */
  words?: ForgotWords;
  form?: FormWords;
}) {
  const [email, setEmail] = useState("");
  const [touched, setTouched] = useState(false);
  const [submitting, setSubmitting] = useState(false);
  const [sent, setSent] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const alertRef = useRef<HTMLDivElement>(null);
  const doneRef = useRef<HTMLParagraphElement>(null);
  const emailRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (error !== null) alertRef.current?.focus();
  }, [error]);
  useEffect(() => {
    if (sent) doneRef.current?.focus();
  }, [sent]);

  const problem = email.trim() === "" ? form.emailMissing : looksLikeEmail(email) ? undefined : form.emailInvalid;
  const emailError = touched ? problem : undefined;

  async function submit() {
    if (submitting) return;
    setTouched(true);
    if (problem !== undefined) {
      emailRef.current?.focus();
      return;
    }
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
    <section aria-labelledby="forgot-heading" className="space-y-6 p-6 sm:p-8">
      <h1 id="forgot-heading" className="heading-5">
        {words.heading}
      </h1>
      {sent ? (
        <p
          ref={doneRef}
          tabIndex={-1}
          role="status"
          className="flex gap-3 rounded-xl border border-success-line bg-success-soft p-4 text-pretty text-slate-900"
        >
          <CircleCheck aria-hidden="true" className="mt-0.5 size-5 shrink-0 text-success" />
          <span>{words.sent}</span>
        </p>
      ) : (
        <>
          <p className="text-pretty text-slate-700">{words.help}</p>
          {error !== null && (
            <ErrorNotice
              id="forgot-error"
              ref={alertRef}
              error={error}
              {...(isRetryable(error) ? { onRetry: () => void submit() } : {})}
            />
          )}
          <form onSubmit={onSubmit} className="space-y-5" noValidate>
            <TextField
              id="forgot-email"
              label={words.email}
              type="email"
              inputMode="email"
              autoComplete="email"
              autoCapitalize="none"
              spellCheck={false}
              required
              value={email}
              onChange={setEmail}
              onBlur={() => setTouched(email.trim() !== "" || touched)}
              error={emailError}
              inputRef={emailRef}
            />
            <Button type="submit" variant="primary" size="lg" className="w-full" loading={submitting}>
              {submitting ? words.sending : words.send}
            </Button>
          </form>
        </>
      )}
      <p className="text-sm text-slate-700">
        <Link href={signInHref} className="font-semibold text-brand-800 underline underline-offset-2">
          {words.back}
        </Link>
      </p>
    </section>
  );
}
