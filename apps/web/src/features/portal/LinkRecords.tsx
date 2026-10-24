"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type FormEvent,
} from "react";

import { Button } from "@/components/ui/Button";
import { Skeleton } from "@/components/ui/Skeleton";
import { ErrorNotice } from "@/features/auth/ErrorNotice";
import { ApiError } from "@/lib/api/client";
import type { components } from "@/lib/api/schema";
import {
  PORTAL_HOME_PATH,
  PORTAL_SIGN_IN_PATH,
  portalGet,
  portalPost,
} from "@/lib/auth/portal-session";

import { portalReasonForEndedSession } from "./messages";

type Invite = components["schemas"]["PortalInvite"];
type Linked = components["schemas"]["PortalLinked"];
type Account = components["schemas"]["PatientAccount"];

export const PRT_INVITE_INVALID = "PRT_INVITE_INVALID";
export const LINK_CHALLENGE_FAILED = "LINK_CHALLENGE_FAILED";

/** Sends a patient whose portal session ended back to sign in, with the reason. */
function useLeave(): [boolean, (error: unknown) => boolean] {
  const router = useRouter();
  const [leaving, setLeaving] = useState(false);
  const leave = useCallback(
    (error: unknown): boolean => {
      const reason = portalReasonForEndedSession(error);
      if (reason === undefined) return false;
      setLeaving(true);
      router.replace(
        `${PORTAL_SIGN_IN_PATH}?${new URLSearchParams({ reason }).toString()}`,
      );
      return true;
    },
    [router],
  );
  return [leaving, leave];
}

function Loading({ label }: Readonly<{ label: string }>) {
  return (
    <section className="space-y-3 p-6 sm:p-8" aria-busy="true">
      <p role="status" className="sr-only">
        {label}
      </p>
      <Skeleton className="h-8 w-2/3" />
      <Skeleton className="h-16 w-full" />
    </section>
  );
}

function Done({ linked }: Readonly<{ linked: Linked }>) {
  return (
    <section
      aria-labelledby="link-done-heading"
      className="space-y-4 p-6 sm:p-8"
    >
      <h1 id="link-done-heading" className="text-2xl font-bold tracking-tight">
        Linked
      </h1>
      <p role="status">
        Your records at {linked.clinic_name} ({linked.patient_first_name} ·{" "}
        {linked.patient_code}) are now in your MediEase account.
      </p>
      <Link
        href={PORTAL_HOME_PATH}
        className="font-medium text-brand-800 underline"
      >
        Go to your account
      </Link>
    </section>
  );
}

/**
 * `/portal/link/{token}` (M6b-P1, FR-PRT-06 b, spec R2-R4): a clinic's invite. The patient sees
 * whose records it is for and confirms, or says it is not them. Nothing links until they do.
 */
export function AcceptInvite({ token }: Readonly<{ token: string }>) {
  const router = useRouter();
  const [leaving, leave] = useLeave();
  const [invite, setInvite] = useState<Invite | undefined>(undefined);
  const [loadError, setLoadError] = useState<unknown>(null);
  const [error, setError] = useState<unknown>(null);
  const [submitting, setSubmitting] = useState(false);
  const [linked, setLinked] = useState<Linked | undefined>(undefined);

  useEffect(() => {
    let cancelled = false;
    portalGet("/api/v1/portal/invites/{token}", { pathParams: { token } }).then(
      ({ data }) => {
        if (!cancelled) setInvite(data);
      },
      (failure: unknown) => {
        if (!cancelled && !leave(failure)) setLoadError(failure);
      },
    );
    return () => {
      cancelled = true;
    };
  }, [token, leave]);

  async function accept() {
    if (submitting) return;
    setSubmitting(true);
    setError(null);
    try {
      const { data } = await portalPost(
        "/api/v1/portal/invites/{token}/accept",
        undefined,
        {
          pathParams: { token },
        },
      );
      setLinked(data);
    } catch (failure) {
      if (!leave(failure)) setError(failure);
      setSubmitting(false);
    }
  }

  if (leaving) return null;
  if (linked !== undefined) return <Done linked={linked} />;
  if (loadError !== null) {
    const invalid =
      loadError instanceof ApiError && loadError.code === PRT_INVITE_INVALID;
    return (
      <section
        aria-labelledby="invite-heading"
        className="space-y-4 p-6 sm:p-8"
      >
        <h1 id="invite-heading" className="text-2xl font-bold tracking-tight">
          {invalid
            ? "This invitation is no longer valid"
            : "Could not open this invitation"}
        </h1>
        {invalid ? (
          <p>
            It may have been used already, replaced by a newer one, or expired.
            Ask the clinic for a new one.
          </p>
        ) : (
          <ErrorNotice error={loadError} />
        )}
        <Link
          href={PORTAL_HOME_PATH}
          className="font-medium text-brand-800 underline"
        >
          Go to your account
        </Link>
      </section>
    );
  }
  if (invite === undefined) return <Loading label="Opening the invitation…" />;

  return (
    <section aria-labelledby="invite-heading" className="space-y-5 p-6 sm:p-8">
      <h1 id="invite-heading" className="text-2xl font-bold tracking-tight">
        Link your records at {invite.clinic_name}
      </h1>
      <p className="text-lg font-semibold">
        {invite.patient_first_name} ·{" "}
        <span className="font-mono">{invite.patient_code}</span>
      </p>
      <p className="text-slate-800">
        Your appointments, prescriptions and reminders from {invite.clinic_name}{" "}
        will appear in this account. Only link records that are yours.
      </p>
      {error !== null && <ErrorNotice error={error} />}
      <div className="flex flex-wrap gap-3">
        <Button
          variant="primary"
          onClick={() => void accept()}
          disabled={submitting}
        >
          {submitting ? "Linking…" : "Link"}
        </Button>
        <Button
          onClick={() => router.replace(PORTAL_HOME_PATH)}
          disabled={submitting}
        >
          Not me
        </Button>
      </div>
    </section>
  );
}

/**
 * `/portal/link/prescription/{token}` (M6b-P1, FR-PRT-06 c, spec R5, R6): the prescription link's
 * last-4 check again, from a verified account. Wrong answers count towards the link's lock, as on
 * the prescription page.
 */
export function LinkFromPrescription({ token }: Readonly<{ token: string }>) {
  const [leaving, leave] = useLeave();
  const [account, setAccount] = useState<Account | undefined>(undefined);
  const [loadError, setLoadError] = useState<unknown>(null);
  const [digits, setDigits] = useState("");
  const [error, setError] = useState<unknown>(null);
  const [submitting, setSubmitting] = useState(false);
  const [linked, setLinked] = useState<Linked | undefined>(undefined);
  const alertRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (error !== null) alertRef.current?.focus();
  }, [error]);

  useEffect(() => {
    let cancelled = false;
    portalGet("/api/v1/portal/me").then(
      ({ data }) => {
        if (!cancelled) setAccount(data.account);
      },
      (failure: unknown) => {
        if (!cancelled && !leave(failure)) setLoadError(failure);
      },
    );
    return () => {
      cancelled = true;
    };
  }, [leave]);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (submitting) return;
    setSubmitting(true);
    setError(null);
    try {
      const { data } = await portalPost("/api/v1/portal/links/prescription", {
        token,
        phone_last4: digits,
      });
      setLinked(data);
    } catch (failure) {
      if (!leave(failure)) {
        setDigits("");
        setError(failure);
      }
      setSubmitting(false);
    }
  }

  if (leaving) return null;
  if (linked !== undefined) return <Done linked={linked} />;
  if (loadError !== null) {
    return (
      <section className="p-6 sm:p-8">
        <ErrorNotice error={loadError} />
      </section>
    );
  }
  if (account === undefined) return <Loading label="Loading your account…" />;

  if (!account.email_verified) {
    return (
      <section
        aria-labelledby="rx-link-heading"
        className="space-y-4 p-6 sm:p-8"
      >
        <h1 id="rx-link-heading" className="text-2xl font-bold tracking-tight">
          Confirm your email first
        </h1>
        <p>
          To save a prescription to your account, confirm your email address
          with the link we sent you, then open this page again. Or ask the
          clinic for an invitation to the patient app.
        </p>
        <Link
          href={PORTAL_HOME_PATH}
          className="font-medium text-brand-800 underline"
        >
          Go to your account
        </Link>
      </section>
    );
  }

  const left =
    error instanceof ApiError && error.code === LINK_CHALLENGE_FAILED
      ? error.details["attempts_left"]
      : undefined;
  return (
    <section aria-labelledby="rx-link-heading" className="space-y-5 p-6 sm:p-8">
      <h1 id="rx-link-heading" className="text-2xl font-bold tracking-tight">
        Save your records to MediEase
      </h1>
      <p className="text-slate-800">
        Enter the last 4 digits of the phone number the clinic has for you. Your
        appointments, prescriptions and reminders from that clinic will then
        appear in this account.
      </p>
      {error !== null && (
        <ErrorNotice
          ref={alertRef}
          error={error}
          {...(typeof left === "string"
            ? { message: `Those digits don't match. ${left} tries left.` }
            : {})}
        />
      )}
      <form onSubmit={(e) => void submit(e)} className="space-y-4">
        <div>
          <label htmlFor="phone_last4" className="block font-medium">
            Last 4 digits of your phone number
          </label>
          <input
            id="phone_last4"
            name="phone_last4"
            type="text"
            inputMode="numeric"
            autoComplete="off"
            pattern="[0-9]{4}"
            minLength={4}
            maxLength={4}
            required
            value={digits}
            onChange={(e) => setDigits(e.target.value)}
            className="mt-1 w-32 rounded border border-slate-600 p-2 text-xl tracking-widest"
          />
        </div>
        <Button type="submit" variant="primary" disabled={submitting}>
          {submitting ? "Saving…" : "Save to my MediEase"}
        </Button>
      </form>
    </section>
  );
}
