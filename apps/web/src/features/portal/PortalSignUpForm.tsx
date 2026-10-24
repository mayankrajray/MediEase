"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState, type FormEvent } from "react";

import { Button } from "@/components/ui/Button";
import { TextField } from "@/components/ui/Field";
import { ErrorNotice } from "@/features/auth/ErrorNotice";
import { GoogleButton } from "@/features/auth/GoogleButton";
import { isRetryable } from "@/features/auth/messages";
import { ApiError, apiPost } from "@/lib/api/client";
import { type PortalLanguage, portalStrings } from "@/lib/i18n/portal";

import { MIN_PASSWORD_LENGTH } from "./messages";

type FieldErrors = Partial<Record<"full_name" | "email" | "password", string>>;

/**
 * Patient sign-up (M6a-P3, FR-PRT-01, ADR-0015 decision 5): a name, an email and a password,
 * then straight into the account. The email is not verified yet; that arrives with the email
 * provider (M6a-P4). Google is offered too.
 */
export function PortalSignUpForm({ next, language = "en" }: { next: string; language?: PortalLanguage }) {
  const s = portalStrings(language);
  const router = useRouter();
  const [fullName, setFullName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [fields, setFields] = useState<FieldErrors>({});
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const submittingRef = useRef(false);
  const alertRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (error !== null) alertRef.current?.focus();
  }, [error]);

  async function submit() {
    if (submittingRef.current) return;
    if (password.length < MIN_PASSWORD_LENGTH) {
      setFields({ password: s.signUp.passwordTooShort });
      return;
    }
    submittingRef.current = true;
    setSubmitting(true);
    setError(null);
    setFields({});
    try {
      await apiPost("/api/v1/portal/auth/sign-up", {
        full_name: fullName.trim(),
        email: email.trim(),
        password,
        language,
      });
      router.replace(next);
    } catch (failure) {
      setFields(fieldErrors(failure));
      setError(failure);
      submittingRef.current = false;
      setSubmitting(false);
    }
  }

  function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    void submit();
  }

  const signInHref = `/portal/sign-in?${new URLSearchParams({ next }).toString()}`;

  return (
    <section aria-labelledby="portal-sign-up-heading" className="space-y-5 p-6 sm:p-8">
      <h1 id="portal-sign-up-heading" className="text-2xl font-bold tracking-tight">
        {s.signUp.heading}
      </h1>
      <p className="text-slate-700">
        {s.signUp.intro}
      </p>

      {error !== null && (
        <ErrorNotice
          id="portal-sign-up-error"
          ref={alertRef}
          error={error}
          {...(isRetryable(error) ? { onRetry: () => void submit() } : {})}
        />
      )}

      <form onSubmit={onSubmit} className="space-y-4" noValidate>
        <TextField
          id="full_name"
          label={s.signUp.name}
          autoComplete="name"
          required
          maxLength={200}
          value={fullName}
          onChange={setFullName}
          error={fields.full_name}
        />
        <TextField
          id="email"
          label={s.signIn.email}
          type="email"
          inputMode="email"
          autoComplete="email"
          required
          maxLength={254}
          value={email}
          onChange={setEmail}
          error={fields.email}
        />
        <TextField
          id="password"
          label={s.signIn.password}
          type="password"
          autoComplete="new-password"
          required
          hint={s.signUp.passwordHelp}
          value={password}
          onChange={setPassword}
          error={fields.password}
        />
        <Button type="submit" variant="primary" className="w-full" disabled={submitting}>
          {submitting ? s.signUp.submitting : s.signUp.submit}
        </Button>
      </form>

      <GoogleButton intent="patient" next={next} email={email} />

      <p className="text-sm text-slate-700">
        {s.signUp.haveAccount}{" "}
        <Link href={signInHref} className="font-medium text-brand-800 underline">
          {s.signUp.signIn}
        </Link>
      </p>
    </section>
  );
}

/** The API's per-field reasons (REQ_VALIDATION_FAILED), for the fields this form has. */
function fieldErrors(error: unknown): FieldErrors {
  if (!(error instanceof ApiError)) return {};
  const listed = error.details.fields;
  if (!Array.isArray(listed)) return {};
  const found: FieldErrors = {};
  for (const item of listed as unknown[]) {
    if (typeof item !== "object" || item === null) continue;
    const { field, reason } = item as { field?: unknown; reason?: unknown };
    if ((field === "full_name" || field === "email" || field === "password") && typeof reason === "string") {
      found[field] = `This ${field === "full_name" ? "name" : field} ${reason}.`;
    }
  }
  return found;
}
