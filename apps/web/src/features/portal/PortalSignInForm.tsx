"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState, type FormEvent } from "react";

import { Button } from "@/components/ui/Button";
import { TextField } from "@/components/ui/Field";
import { ErrorNotice } from "@/features/auth/ErrorNotice";
import { GoogleButton } from "@/features/auth/GoogleButton";
import { AUTH_LOCKED, isRetryable } from "@/features/auth/messages";
import { ApiError, apiPost } from "@/lib/api/client";

import { PORTAL_SIGN_IN_REASONS, PRT_INVALID_CREDENTIALS, type PortalSignInReason } from "./messages";

/**
 * Patient sign-in (M6a-P3, FR-PRT-01): email and password, or Google. A separate page and a
 * separate session from staff sign-in (ADR-0015 decisions 2, 8), so neither sees the other's
 * options. `next` has already passed `safePortalNextPath` on the server.
 */
export function PortalSignInForm({ next, reason }: { next: string; reason?: PortalSignInReason }) {
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const submittingRef = useRef(false);
  const alertRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (error !== null) alertRef.current?.focus();
  }, [error]);

  async function submit() {
    if (submittingRef.current) return;
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

  return (
    <section aria-labelledby="portal-sign-in-heading" className="space-y-5 p-6 sm:p-8">
      <h1 id="portal-sign-in-heading" className="text-2xl font-bold tracking-tight">
        Sign in to your health account
      </h1>

      {reason !== undefined && error === null && (
        <p role="status" className="rounded-lg border border-slate-300 bg-slate-50 p-3">
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

      <form onSubmit={onSubmit} className="space-y-4">
        <TextField
          id="portal-email"
          label="Email"
          type="email"
          inputMode="email"
          autoComplete="email"
          required
          value={email}
          onChange={setEmail}
        />
        <TextField
          id="portal-password"
          label="Password"
          type="password"
          autoComplete="current-password"
          required
          value={password}
          onChange={setPassword}
        />
        <Button type="submit" variant="primary" className="w-full" disabled={submitting}>
          {submitting ? "Signing in…" : "Sign in"}
        </Button>
      </form>

      <GoogleButton intent="patient" next={next} email={email} />

      <p className="text-sm text-slate-700">
        New to MediEase?{" "}
        <Link href={signUpHref} className="font-medium text-brand-800 underline">
          Create an account
        </Link>
      </p>
    </section>
  );
}
