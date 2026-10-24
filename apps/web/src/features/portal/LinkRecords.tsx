"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useRef, useState, type FormEvent } from "react";

import { Button } from "@/components/ui/Button";
import { ErrorNotice } from "@/features/auth/ErrorNotice";
import { ApiError } from "@/lib/api/client";
import type { components } from "@/lib/api/schema";
import { PORTAL_HOME_PATH, portalGet, portalPost } from "@/lib/auth/portal-session";

import { portalErrorText, usePortalLoad } from "./data";
import { ScreenLoading, usePortal } from "./PortalShell";

type Invite = components["schemas"]["PortalInvite"];
type Linked = components["schemas"]["PortalLinked"];

export const PRT_INVITE_INVALID = "PRT_INVITE_INVALID";

function Done({ linked }: Readonly<{ linked: Linked }>) {
  const { s } = usePortal();
  return (
    <section aria-labelledby="link-done-heading" className="space-y-4">
      <h1 id="link-done-heading" className="text-2xl font-bold tracking-tight">
        {s.link.done}
      </h1>
      <p role="status">{s.link.doneHelp(linked.clinic_name, `${linked.patient_first_name} · ${linked.patient_code}`)}</p>
      <Link href={PORTAL_HOME_PATH} className="inline-flex min-h-11 items-center font-medium text-brand-800 underline">
        {s.link.goAccount}
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
  const { s, leave } = usePortal();
  const load = useCallback(
    async (): Promise<Invite> => (await portalGet("/api/v1/portal/invites/{token}", { pathParams: { token } })).data,
    [token],
  );
  const invite = usePortalLoad(load);
  const [error, setError] = useState<unknown>(null);
  const [submitting, setSubmitting] = useState(false);
  const [linked, setLinked] = useState<Linked | undefined>(undefined);

  async function accept() {
    if (submitting) return;
    setSubmitting(true);
    setError(null);
    try {
      const { data } = await portalPost("/api/v1/portal/invites/{token}/accept", undefined, { pathParams: { token } });
      setLinked(data);
    } catch (failure) {
      if (!leave(failure)) setError(failure);
      setSubmitting(false);
    }
  }

  if (linked !== undefined) return <Done linked={linked} />;
  if (invite.status === "loading") return <ScreenLoading label={s.loading} />;
  if (invite.status === "failed") {
    const invalid = invite.error instanceof ApiError && invite.error.code === PRT_INVITE_INVALID;
    return (
      <section aria-labelledby="invite-heading" className="space-y-4">
        <h1 id="invite-heading" className="text-2xl font-bold tracking-tight">
          {invalid ? s.link.invalidTitle : s.link.couldNotOpen}
        </h1>
        {invalid ? <p>{s.link.invalid}</p> : <ErrorNotice error={invite.error} onRetry={invite.retry} />}
        <Link href={PORTAL_HOME_PATH} className="inline-flex min-h-11 items-center font-medium text-brand-800 underline">
          {s.link.goAccount}
        </Link>
      </section>
    );
  }
  const text = portalErrorText(error, s);
  return (
    <section aria-labelledby="invite-heading" className="space-y-5">
      <h1 id="invite-heading" className="text-2xl font-bold tracking-tight">
        {s.link.heading(invite.data.clinic_name)}
      </h1>
      <p className="text-lg font-semibold">
        {invite.data.patient_first_name} · <span className="font-mono">{invite.data.patient_code}</span>
      </p>
      <p className="text-slate-800">{s.link.help(invite.data.clinic_name)}</p>
      {error !== null && <ErrorNotice error={error} {...(text === undefined ? {} : { message: text })} />}
      <div className="flex flex-wrap gap-3">
        <Button variant="primary" onClick={() => void accept()} disabled={submitting}>
          {submitting ? s.link.linking : s.link.link}
        </Button>
        <Button onClick={() => router.replace(PORTAL_HOME_PATH)} disabled={submitting}>
          {s.link.notMe}
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
  const { account, s, leave } = usePortal();
  const [digits, setDigits] = useState("");
  const [error, setError] = useState<unknown>(null);
  const [submitting, setSubmitting] = useState(false);
  const [linked, setLinked] = useState<Linked | undefined>(undefined);
  const alertRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (error !== null) alertRef.current?.focus();
  }, [error]);

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (submitting) return;
    setSubmitting(true);
    setError(null);
    try {
      const { data } = await portalPost("/api/v1/portal/links/prescription", { token, phone_last4: digits });
      setLinked(data);
    } catch (failure) {
      if (!leave(failure)) {
        setDigits("");
        setError(failure);
      }
      setSubmitting(false);
    }
  }

  if (linked !== undefined) return <Done linked={linked} />;
  if (!account.email_verified) {
    return (
      <section aria-labelledby="rx-link-heading" className="space-y-4">
        <h1 id="rx-link-heading" className="text-2xl font-bold tracking-tight">
          {s.link.verifyFirst}
        </h1>
        <p>{s.link.verifyFirstHelp}</p>
        <Link href="/portal/account" className="inline-flex min-h-11 items-center font-medium text-brand-800 underline">
          {s.nav.account}
        </Link>
      </section>
    );
  }

  const text = portalErrorText(error, s);
  return (
    <section aria-labelledby="rx-link-heading" className="space-y-5">
      <h1 id="rx-link-heading" className="text-2xl font-bold tracking-tight">
        {s.link.rxHeading}
      </h1>
      <p className="text-slate-800">{s.link.rxHelp}</p>
      {error !== null && <ErrorNotice ref={alertRef} error={error} {...(text === undefined ? {} : { message: text })} />}
      <form onSubmit={(e) => void submit(e)} className="space-y-4">
        <div>
          <label htmlFor="phone_last4" className="block font-medium">
            {s.link.last4}
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
            className="mt-1 min-h-11 w-32 rounded border border-slate-600 p-2 text-xl tracking-widest"
          />
        </div>
        <Button type="submit" variant="primary" disabled={submitting}>
          {submitting ? s.link.saving : s.link.save}
        </Button>
      </form>
    </section>
  );
}
