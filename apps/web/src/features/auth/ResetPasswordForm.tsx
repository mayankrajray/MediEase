"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState, type FormEvent } from "react";

import { Button } from "@/components/ui/Button";
import { TextField } from "@/components/ui/Field";
import { ApiError, apiPost } from "@/lib/api/client";
import { RESET_EN, type ResetWords } from "@/lib/i18n/portal";

import { ErrorNotice } from "./ErrorNotice";
import type { AccountKind } from "./ForgotPasswordForm";
import { isRetryable } from "./messages";

export const AUTH_TOKEN_INVALID = "AUTH_TOKEN_INVALID";
export const AUTH_TOKEN_EXPIRED = "AUTH_TOKEN_EXPIRED";
const MIN_LENGTH = 12;

const COMPLETE_PATH = {
  staff: "/api/v1/auth/password-reset/complete",
  patient: "/api/v1/portal/auth/password-reset/complete",
} as const;

/**
 * Choosing a new password from the emailed link (M6a-P4, ADR-0016 decision 7). The token comes
 * from the URL and is only ever sent back in this POST. Success ends every session and returns
 * to sign-in; it never signs in by itself.
 */
export function ResetPasswordForm({
  kind,
  token,
  signInPath,
  forgotPath,
  words = RESET_EN,
}: {
  kind: AccountKind;
  token: string;
  signInPath: string;
  forgotPath: string;
  /** The patient pages pass Hindi when the portal's language is Hindi (M6b-P2); staff keep English. */
  words?: ResetWords;
}) {
  const router = useRouter();
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [fieldError, setFieldError] = useState<string | undefined>(undefined);
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const alertRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (error !== null) alertRef.current?.focus();
  }, [error]);

  async function submit() {
    if (submitting) return;
    if (password.length < MIN_LENGTH) {
      setFieldError(words.tooShort);
      return;
    }
    if (password !== confirm) {
      setFieldError(words.different);
      return;
    }
    setFieldError(undefined);
    setSubmitting(true);
    setError(null);
    try {
      await apiPost(COMPLETE_PATH[kind], { token, password });
      router.replace(`${signInPath}?reason=password_reset`);
    } catch (failure) {
      setError(failure);
      setSubmitting(false);
    }
  }

  function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    void submit();
  }

  const linkGone =
    error instanceof ApiError && (error.code === AUTH_TOKEN_INVALID || error.code === AUTH_TOKEN_EXPIRED);

  return (
    <section aria-labelledby="reset-heading" className="space-y-5 p-6 sm:p-8">
      <h1 id="reset-heading" className="text-2xl font-bold tracking-tight">
        {words.heading}
      </h1>
      {error !== null && (
        <ErrorNotice
          id="reset-error"
          ref={alertRef}
          error={error}
          {...(isRetryable(error) ? { onRetry: () => void submit() } : {})}
        />
      )}
      {linkGone ? (
        <p>
          <Link href={forgotPath} className="font-medium text-brand-800 underline">
            {words.newLink}
          </Link>
        </p>
      ) : (
        <form onSubmit={onSubmit} className="space-y-4" noValidate>
          <TextField
            id="new-password"
            label={words.newPassword}
            type="password"
            autoComplete="new-password"
            required
            hint={words.hint}
            value={password}
            onChange={setPassword}
            error={fieldError}
          />
          <TextField
            id="confirm-password"
            label={words.again}
            type="password"
            autoComplete="new-password"
            required
            value={confirm}
            onChange={setConfirm}
          />
          <Button type="submit" variant="primary" className="w-full" disabled={submitting}>
            {submitting ? words.saving : words.save}
          </Button>
        </form>
      )}
    </section>
  );
}
