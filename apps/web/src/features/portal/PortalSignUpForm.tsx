"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState, type FormEvent } from "react";

import { Button } from "@/components/ui/Button";
import { looksLikeEmail, PasswordField, TextField } from "@/components/ui/Field";
import { ErrorNotice } from "@/features/auth/ErrorNotice";
import { GoogleButton } from "@/features/auth/GoogleButton";
import { isRetryable } from "@/features/auth/messages";
import { ApiError, apiPost } from "@/lib/api/client";
import { formWords, type PortalLanguage, portalStrings } from "@/lib/i18n/portal";

import { MIN_PASSWORD_LENGTH } from "./messages";

type FieldErrors = Partial<Record<"full_name" | "email" | "password", string>>;
type Field = keyof FieldErrors;

/**
 * Creating a patient account with email and password (M6a-P3, FR-PRT-01), or with Google. The
 * account starts unlinked; the patient's records join it later (M6b).
 *
 * M7c-P7 (M2; DESIGN.md §8a): each field is checked when the person leaves it and re-checked as
 * they type a fix (name present, an email-shaped address, the 12-character rule ticking off);
 * the name shows how many of its 200 characters are used; a failed submit moves focus to the
 * first field with a problem and keeps everything typed. The API remains the judge: its own
 * field reasons appear under the fields too.
 */
export function PortalSignUpForm({ next, language = "en" }: { next: string; language?: PortalLanguage }) {
  const s = portalStrings(language);
  const f = formWords(language);
  const router = useRouter();
  const [fullName, setFullName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [touched, setTouched] = useState<Record<Field, boolean>>({ full_name: false, email: false, password: false });
  const [server, setServer] = useState<FieldErrors>({});
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const submittingRef = useRef(false);
  const alertRef = useRef<HTMLDivElement>(null);
  const nameRef = useRef<HTMLInputElement>(null);
  const emailRef = useRef<HTMLInputElement>(null);
  const passwordRef = useRef<HTMLInputElement>(null);

  useEffect(() => {
    if (error !== null) alertRef.current?.focus();
  }, [error]);

  const longEnough = password.length >= MIN_PASSWORD_LENGTH;
  const problems: FieldErrors = {
    ...(fullName.trim() === "" ? { full_name: f.nameMissing } : {}),
    ...(email.trim() === "" ? { email: f.emailMissing } : looksLikeEmail(email) ? {} : { email: f.emailInvalid }),
    ...(longEnough ? {} : { password: s.signUp.passwordTooShort }),
  };
  const shown = (field: Field): string | undefined => (touched[field] ? problems[field] : undefined) ?? server[field];
  const leave = (field: Field, value: string) => () => setTouched((t) => ({ ...t, [field]: t[field] || value !== "" }));
  const change = (field: Field, set: (v: string) => void) => (value: string) => {
    set(value);
    setServer((current) => {
      const rest = { ...current };
      delete rest[field];
      return rest;
    });
  };

  async function submit() {
    if (submittingRef.current) return;
    const first = (["full_name", "email", "password"] as const).find((field) => problems[field] !== undefined);
    if (first !== undefined) {
      setTouched({ full_name: true, email: true, password: true });
      ({ full_name: nameRef, email: emailRef, password: passwordRef })[first].current?.focus();
      return;
    }
    submittingRef.current = true;
    setSubmitting(true);
    setError(null);
    setServer({});
    try {
      await apiPost("/api/v1/portal/auth/sign-up", {
        full_name: fullName.trim(),
        email: email.trim(),
        password,
        language,
      });
      router.replace(next);
    } catch (failure) {
      setServer(fieldErrors(failure));
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
    <section aria-labelledby="portal-sign-up-heading" className="space-y-6 p-6 sm:p-8">
      <div className="space-y-1">
        <h1 id="portal-sign-up-heading" className="heading-5">
          {s.signUp.heading}
        </h1>
        <p className="text-pretty text-slate-700">{s.signUp.intro}</p>
      </div>

      {error !== null && (
        <ErrorNotice
          id="portal-sign-up-error"
          ref={alertRef}
          error={error}
          {...(isRetryable(error) ? { onRetry: () => void submit() } : {})}
        />
      )}

      <form onSubmit={onSubmit} className="space-y-5" noValidate>
        <TextField
          id="full_name"
          label={s.signUp.name}
          autoComplete="name"
          required
          maxLength={200}
          counter
          value={fullName}
          onChange={change("full_name", setFullName)}
          onBlur={leave("full_name", fullName)}
          error={shown("full_name")}
          inputRef={nameRef}
        />
        <TextField
          id="email"
          label={s.signIn.email}
          type="email"
          inputMode="email"
          autoComplete="email"
          autoCapitalize="none"
          spellCheck={false}
          required
          maxLength={254}
          value={email}
          onChange={change("email", setEmail)}
          onBlur={leave("email", email)}
          error={shown("email")}
          inputRef={emailRef}
        />
        <PasswordField
          id="password"
          label={s.signIn.password}
          autoComplete="new-password"
          required
          hint={s.signUp.passwordHelp}
          value={password}
          onChange={change("password", setPassword)}
          onBlur={leave("password", password)}
          error={shown("password")}
          inputRef={passwordRef}
          requirements={[{ label: f.ruleLength, met: longEnough }]}
          showLabel={f.show}
          hideLabel={f.hide}
          metLabel={f.met}
          unmetLabel={f.unmet}
        />
        <Button type="submit" variant="primary" size="lg" className="w-full" loading={submitting}>
          {submitting ? s.signUp.submitting : s.signUp.submit}
        </Button>
      </form>

      <GoogleButton intent="patient" next={next} email={email} />

      <p className="text-center text-sm text-slate-700">
        {s.signUp.haveAccount}{" "}
        <Link href={signInHref} className="font-semibold text-brand-800 underline underline-offset-2">
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
