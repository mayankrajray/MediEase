"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState, type FormEvent } from "react";

import { Button } from "@/components/ui/Button";
import { looksLikeEmail, PasswordField, TextField } from "@/components/ui/Field";
import { ErrorNotice } from "@/features/auth/ErrorNotice";
import { GoogleButton } from "@/features/auth/GoogleButton";
import { AUTH_LOCKED, isRetryable } from "@/features/auth/messages";
import { ApiError, apiPost } from "@/lib/api/client";
import { formWords, type PortalLanguage, portalStrings } from "@/lib/i18n/portal";

import { PORTAL_SIGN_IN_REASONS, PRT_INVALID_CREDENTIALS, type PortalSignInReason } from "./messages";

/**
 * Patient sign-in (M6a-P3, FR-PRT-01): email and password, or Google. A separate page and a
 * separate session from staff sign-in (ADR-0015 decisions 2, 8), so neither sees the other's
 * options. `next` has already passed `safePortalNextPath` on the server.
 *
 * M7c-P7 (M2; DESIGN.md §8a): the email is checked when the person leaves it and both fields
 * before sending, with the reason under the field in the page's language; the password can be
 * shown; a wrong password keeps the email and marks the password.
 */
export function PortalSignInForm({
  next,
  reason,
  language = "en",
}: {
  next: string;
  reason?: PortalSignInReason;
  language?: PortalLanguage;
}) {
  const s = portalStrings(language);
  const f = formWords(language);
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [touched, setTouched] = useState({ email: false, password: false });
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const submittingRef = useRef(false);
  const alertRef = useRef<HTMLDivElement>(null);
  const emailRef = useRef<HTMLInputElement>(null);
  const passwordRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (error !== null) alertRef.current?.focus();
  }, [error]);

  const emailProblem = email.trim() === "" ? f.emailMissing : looksLikeEmail(email) ? undefined : f.emailInvalid;
  const passwordProblem = password === "" ? f.passwordMissing : undefined;

  async function submit() {
    if (submittingRef.current) return;
    if (emailProblem !== undefined || passwordProblem !== undefined) {
      setTouched({ email: true, password: true });
      (emailProblem !== undefined ? emailRef : passwordRef).current?.focus();
      return;
    }
    submittingRef.current = true;
    setSubmitting(true);
    setError(null);
    try {
      await apiPost("/api/v1/portal/auth/sign-in", { email: email.trim(), password });
      router.replace(next);
    } catch (failure) {
      if (
        failure instanceof ApiError &&
        (failure.code === PRT_INVALID_CREDENTIALS || failure.code === AUTH_LOCKED)
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

  const signUpHref = `/portal/sign-up?${new URLSearchParams({ next }).toString()}`;
  const invalid = error instanceof ApiError && error.code === PRT_INVALID_CREDENTIALS;
  const errorId = error !== null ? "portal-sign-in-error" : undefined;

  return (
    <section aria-labelledby="portal-sign-in-heading" className="space-y-6 p-6 sm:p-8">
      <h1 id="portal-sign-in-heading" className="heading-5">
        {s.signIn.heading}
      </h1>

      {reason !== undefined && error === null && (
        <p role="status" className="rounded-xl border border-info-line bg-info-soft p-4 text-pretty text-slate-900">
          {PORTAL_SIGN_IN_REASONS[reason]}
        </p>
      )}

      {error !== null && (
        <ErrorNotice
          id="portal-sign-in-error"
          ref={alertRef}
          error={error}
          {...(isRetryable(error) ? { onRetry: () => void submit() } : {})}
        />
      )}

      <form onSubmit={onSubmit} className="space-y-5" noValidate>
        <TextField
          id="portal-email"
          label={s.signIn.email}
          type="email"
          inputMode="email"
          autoComplete="email"
          autoCapitalize="none"
          spellCheck={false}
          required
          requiredMark={false}
          value={email}
          onChange={setEmail}
          onBlur={() => setTouched((t) => ({ ...t, email: t.email || email !== "" }))}
          error={touched.email ? emailProblem : undefined}
          describedBy={errorId}
          inputRef={emailRef}
        />
        <PasswordField
          id="portal-password"
          label={s.signIn.password}
          autoComplete="current-password"
          required
          requiredMark={false}
          value={password}
          onChange={setPassword}
          error={touched.password && !invalid ? passwordProblem : undefined}
          invalid={invalid}
          describedBy={errorId}
          inputRef={passwordRef}
          showLabel={f.show}
          hideLabel={f.hide}
        />
        <Button type="submit" variant="primary" size="lg" className="w-full" loading={submitting}>
          {submitting ? s.signIn.submitting : s.signIn.submit}
        </Button>
      </form>

      <p className="text-center text-sm text-slate-700">
        <Link href="/portal/forgot-password" className="font-semibold text-brand-800 underline underline-offset-2">
          {s.signIn.forgot}
        </Link>
      </p>

      <GoogleButton intent="patient" next={next} email={email} />

      <p className="text-center text-sm text-slate-700">
        {s.signIn.newHere}{" "}
        <Link href={signUpHref} className="font-semibold text-brand-800 underline underline-offset-2">
          {s.signIn.create}
        </Link>
      </p>
    </section>
  );
}
