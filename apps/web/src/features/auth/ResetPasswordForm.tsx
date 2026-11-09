"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState, type FormEvent } from "react";

import { Button } from "@/components/ui/Button";
import { PasswordField } from "@/components/ui/Field";
import { ErrorNotice } from "@/features/auth/ErrorNotice";
import { isRetryable } from "@/features/auth/messages";
import { apiPost, ApiError } from "@/lib/api/client";
import { FORM_EN, RESET_EN, type FormWords, type ResetWords } from "@/lib/i18n/portal";

import type { AccountKind } from "./ForgotPasswordForm";

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
 *
 * M7c-P7 (M2; DESIGN.md §8a): the rules tick off as the person types; each field is checked when
 * they leave it and re-checked as they fix it; the "not the same" message sits on the second
 * field; a failed submit moves focus to the first field with a problem. The API is the judge.
 */
export function ResetPasswordForm({
  kind,
  token,
  signInPath,
  forgotPath,
  words = RESET_EN,
  form = FORM_EN,
}: {
  kind: AccountKind;
  token: string;
  signInPath: string;
  forgotPath: string;
  /** The patient pages pass Hindi when the portal's language is Hindi (M6b-P2); staff keep English. */
  words?: ResetWords;
  form?: FormWords;
}) {
  const router = useRouter();
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [touched, setTouched] = useState({ password: false, confirm: false });
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const alertRef = useRef<HTMLDivElement>(null);
  const passwordRef = useRef<HTMLInputElement>(null);
  const confirmRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (error !== null) alertRef.current?.focus();
  }, [error]);

  const longEnough = password.length >= MIN_LENGTH;
  const same = confirm !== "" && confirm === password;
  const passwordError = touched.password && !longEnough ? words.tooShort : undefined;
  const confirmError = touched.confirm && longEnough && !same ? words.different : undefined;

  async function submit() {
    if (submitting) return;
    setTouched({ password: true, confirm: true });
    if (!longEnough) {
      passwordRef.current?.focus();
      return;
    }
    if (!same) {
      confirmRef.current?.focus();
      return;
    }
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
    <section aria-labelledby="reset-heading" className="space-y-6 p-6 sm:p-8">
      <h1 id="reset-heading" className="heading-5">
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
          <Link href={forgotPath} className="font-semibold text-brand-800 underline underline-offset-2">
            {words.newLink}
          </Link>
        </p>
      ) : (
        <form onSubmit={onSubmit} className="space-y-5" noValidate>
          <PasswordField
            id="new-password"
            label={words.newPassword}
            autoComplete="new-password"
            required
            hint={words.hint}
            value={password}
            onChange={setPassword}
            onBlur={() => setTouched((t) => ({ ...t, password: password !== "" || t.password }))}
            error={passwordError}
            inputRef={passwordRef}
            requirements={[{ label: form.ruleLength, met: longEnough }]}
            showLabel={form.show}
            hideLabel={form.hide}
            metLabel={form.met}
            unmetLabel={form.unmet}
          />
          <PasswordField
            id="confirm-password"
            label={words.again}
            autoComplete="new-password"
            required
            value={confirm}
            onChange={setConfirm}
            onBlur={() => setTouched((t) => ({ ...t, confirm: confirm !== "" || t.confirm }))}
            error={confirmError}
            inputRef={confirmRef}
            requirements={[{ label: form.ruleMatch, met: same }]}
            showLabel={form.show}
            hideLabel={form.hide}
            metLabel={form.met}
            unmetLabel={form.unmet}
          />
          <Button type="submit" variant="primary" size="lg" className="w-full" loading={submitting}>
            {submitting ? words.saving : words.save}
          </Button>
        </form>
      )}
    </section>
  );
}
