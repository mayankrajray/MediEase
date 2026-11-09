"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useRef, useState, type FormEvent } from "react";

import { Button } from "@/components/ui/Button";
import { PasswordField } from "@/components/ui/Field";
import { Skeleton } from "@/components/ui/Skeleton";
import { ApiError, apiGet, apiPost, type GetResponse } from "@/lib/api/client";
import { FORM_EN } from "@/lib/i18n/portal";

import { readRememberedClinic } from "./clinic-selection";
import { ErrorNotice } from "./ErrorNotice";
import { ROLE_LABELS } from "./labels";
import { TODAY_PATH, postSignInPath } from "./landing";
import {
  AUTH_INVALID_CREDENTIALS,
  AUTH_LOCKED,
  formatWait,
  isRetryable,
} from "./messages";

type Invite = GetResponse<"/api/v1/auth/invites/{token}">;

type Load =
  | { readonly status: "loading" }
  | { readonly status: "ready"; readonly invite: Invite }
  | { readonly status: "failed"; readonly error: unknown };

const MIN_LENGTH = 12;

/**
 * Accepting a staff invitation (FR-ORG-04): describe the invite, ask for a
 * password, accept, and land signed in. The page is public; the secret in the URL
 * is needed but, for an account that already exists, not enough: that person
 * enters their current password, which is checked and never changed (spec R13).
 * The 12-character minimum for a new password is only a hint, the API decides.
 */
export function AcceptInviteForm({ token }: { token: string }) {
  const router = useRouter();
  const [load, setLoad] = useState<Load>({ status: "loading" });
  const [attempt, setAttempt] = useState(0);
  const [password, setPassword] = useState("");
  const [confirmation, setConfirmation] = useState("");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [mismatch, setMismatch] = useState(false);
  const [tried, setTried] = useState(false);
  const submittingRef = useRef(false);
  const alertRef = useRef<HTMLDivElement>(null);
  const passwordRef = useRef<HTMLInputElement>(null);
  const confirmRef = useRef<HTMLInputElement>(null);
  const existing = load.status === "ready" && load.invite.has_password;
  const longEnough = password.length >= MIN_LENGTH;

  useEffect(() => {
    let cancelled = false;
    apiGet("/api/v1/auth/invites/{token}", { pathParams: { token } }).then(
      ({ data }) => {
        if (!cancelled) setLoad({ status: "ready", invite: data });
      },
      (failure: unknown) => {
        if (!cancelled) setLoad({ status: "failed", error: failure });
      },
    );
    return () => {
      cancelled = true;
    };
  }, [token, attempt]);

  useEffect(() => {
    if (error === null) return;
    const wrongPassword = error instanceof ApiError && error.code === AUTH_INVALID_CREDENTIALS;
    (wrongPassword ? passwordRef.current : alertRef.current)?.focus();
  }, [error]);

  function retryLoad() {
    setLoad({ status: "loading" });
    setAttempt((n) => n + 1);
  }

  async function submit() {
    if (submittingRef.current) return;
    setTried(true);
    if (existing && password === "") {
      passwordRef.current?.focus();
      return;
    }
    if (!existing && password.length < MIN_LENGTH) {
      passwordRef.current?.focus();
      return;
    }
    if (!existing && password !== confirmation) {
      setMismatch(true);
      confirmRef.current?.focus();
      return;
    }
    setMismatch(false);
    submittingRef.current = true;
    setSubmitting(true);
    setError(null);
    try {
      const { data } = await apiPost(
        "/api/v1/auth/invites/{token}/accept",
        { password },
        { pathParams: { token } },
      );
      router.replace(postSignInPath(data, readRememberedClinic(), TODAY_PATH));
    } catch (failure) {
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

  if (load.status === "loading") {
    return (
      <section className="space-y-4 p-6 sm:p-8">
        <p role="status" className="text-slate-700">
          Checking your invitation…
        </p>
        <Skeleton className="h-8 w-2/3" />
        <Skeleton className="h-5 w-full" />
        <Skeleton className="h-10 w-full" />
      </section>
    );
  }

  if (load.status === "failed") {
    // 404 unknown, 410 expired or already used: the API says which, in words.
    const gone = load.error instanceof ApiError && (load.error.status === 404 || load.error.status === 410);
    return (
      <section aria-labelledby="invite-heading" className="space-y-5 p-6 sm:p-8">
        <h1 id="invite-heading" className="heading-5">
          Invitation
        </h1>
        <ErrorNotice error={load.error} {...(isRetryable(load.error) ? { onRetry: retryLoad } : {})} />
        {gone && (
          <p className="text-pretty text-slate-700">
            Ask your clinic for a new invitation, or{" "}
            <Link href="/sign-in" className="font-semibold text-brand-800 underline underline-offset-2">
              sign in
            </Link>{" "}
            if you have already joined.
          </p>
        )}
      </section>
    );
  }

  const { invite } = load;
  const wrongPassword = error instanceof ApiError && error.code === AUTH_INVALID_CREDENTIALS;
  const lockedMessage =
    error instanceof ApiError && error.code === AUTH_LOCKED && error.retryAfterSeconds !== undefined
      ? `Too many attempts. Try again in ${formatWait(error.retryAfterSeconds)}.`
      : undefined;
  return (
    <section aria-labelledby="invite-heading" className="space-y-6 p-6 sm:p-8">
      <div className="space-y-1">
        <h1 id="invite-heading" className="heading-5">
          Join {invite.clinic_name}
        </h1>
        <p className="text-pretty text-slate-700">
          {invite.full_name}, you have been invited as <strong className="text-slate-900">{ROLE_LABELS[invite.role]}</strong>.
        </p>
      </div>

      {error !== null && (
        <ErrorNotice
          id="invite-error"
          ref={alertRef}
          error={error}
          {...(lockedMessage === undefined ? {} : { message: lockedMessage })}
        />
      )}

      <form onSubmit={onSubmit} className="space-y-5" noValidate>
        {invite.has_password ? (
          // An account that already exists keeps its password (spec R13): the person proves
          // it is theirs by entering it, and nothing is set or changed.
          <>
            <p id="existing-hint" className="rounded-xl border border-info-line bg-info-soft p-4 text-sm text-pretty text-slate-900">
              You already have a MediEase account, so you keep your password. Enter it to join{" "}
              {invite.clinic_name}.
            </p>
            <PasswordField
              id="current-password"
              label="Your MediEase password"
              autoComplete="current-password"
              required
              requiredMark={false}
              value={password}
              onChange={setPassword}
              invalid={wrongPassword}
              error={tried && password === "" ? FORM_EN.passwordMissing : undefined}
              describedBy={error !== null ? "invite-error" : "existing-hint"}
              inputRef={passwordRef}
            />
          </>
        ) : (
          <>
            <PasswordField
              id="new-password"
              label="Choose a password"
              autoComplete="new-password"
              required
              requiredMark={false}
              hint={`At least ${MIN_LENGTH} characters.`}
              value={password}
              onChange={setPassword}
              error={tried && !longEnough ? `Use at least ${MIN_LENGTH} characters.` : undefined}
              requirements={[{ label: FORM_EN.ruleLength, met: longEnough }]}
              inputRef={passwordRef}
            />
            <PasswordField
              id="confirm-password"
              label="Type it again"
              autoComplete="new-password"
              required
              requiredMark={false}
              value={confirmation}
              onChange={(value) => {
                setConfirmation(value);
                setMismatch(false);
              }}
              error={mismatch ? "The two passwords are not the same." : undefined}
              errorLive
              requirements={[{ label: FORM_EN.ruleMatch, met: confirmation !== "" && confirmation === password }]}
              inputRef={confirmRef}
            />
          </>
        )}
        <Button type="submit" variant="primary" size="lg" className="w-full" loading={submitting}>
          {submitting ? "Joining…" : invite.has_password ? "Join" : "Set password and join"}
        </Button>
      </form>
    </section>
  );
}