"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

import { Button } from "@/components/ui/Button";
import { ErrorNotice } from "@/features/auth/ErrorNotice";
import { PORTAL_SIGN_IN_PATH, portalDelete, portalGet, portalPatch, portalPost } from "@/lib/auth/portal-session";
import { type PortalLanguage, portalDate } from "@/lib/i18n/portal";

import { type PortalLink, usePortalLoad } from "./data";
import { PortalCard, ScreenLoading, usePortal } from "./PortalShell";

async function loadLinks(): Promise<readonly PortalLink[]> {
  return (await portalGet("/api/v1/portal/links")).data.items;
}

const LANGUAGES: readonly { value: PortalLanguage; label: string }[] = [
  { value: "en", label: "English" },
  { value: "hi", label: "हिन्दी" },
];

/**
 * *Account* (M6b-P2, decision 7A; spec R20, R21): who is signed in, the language, the linked
 * clinics with *Unlink* behind a confirmation, and sign-out.
 */
export function PortalAccountPage() {
  const router = useRouter();
  const { account, s, setLanguage, leave } = usePortal();
  const links = usePortalLoad(loadLinks);
  const [hidden, setHidden] = useState<ReadonlySet<string>>(new Set());
  const [confirming, setConfirming] = useState<string | null>(null);
  const [status, setStatus] = useState("");
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);

  async function unlink(link: PortalLink) {
    if (busy) return;
    setBusy(true);
    setError(null);
    try {
      await portalDelete("/api/v1/portal/links/{link_id}", { pathParams: { link_id: link.id } });
      setHidden((old) => new Set([...old, link.id]));
      setConfirming(null);
      setStatus(s.account.unlinked(link.clinic.name));
    } catch (failure) {
      if (!leave(failure)) setError(failure);
    } finally {
      setBusy(false);
    }
  }

  async function chooseLanguage(language: PortalLanguage) {
    setError(null);
    try {
      await setLanguage(language);
    } catch (failure) {
      if (!leave(failure)) setError(failure);
    }
  }

  async function signOut() {
    setBusy(true);
    try {
      await portalPost("/api/v1/portal/auth/sign-out", undefined);
    } catch {
      // The session may already be gone; leaving must still work.
    }
    router.replace(PORTAL_SIGN_IN_PATH);
  }

  const shown = links.status === "ready" ? links.data.filter((l) => !hidden.has(l.id)) : [];

  return (
    <div className="space-y-5">
      <h1 className="text-2xl font-bold tracking-tight">{s.account.title}</h1>
      {error !== null && <ErrorNotice error={error} />}
      <p role="status" className="min-h-6">
        {status}
      </p>

      <PortalCard id="profile-heading" title={account.full_name}>
        <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-2">
          <dt className="font-medium">{s.account.email}</dt>
          <dd className="break-all">
            {account.email} · <span>{account.email_verified ? s.account.verified : s.account.notVerified}</span>
          </dd>
          <dt className="font-medium">{s.account.signsInWith}</dt>
          <dd>{account.sign_in_method === "GOOGLE" ? s.account.google : s.account.password}</dd>
        </dl>
        {!account.email_verified && account.sign_in_method === "PASSWORD" && <VerifyBanner />}
      </PortalCard>

      <PortalCard id="language-heading" title={s.account.language}>
        <fieldset>
          <legend className="sr-only">{s.account.language}</legend>
          <div className="flex gap-4">
            {LANGUAGES.map((l) => (
              <label key={l.value} lang={l.value} className="flex min-h-11 items-center gap-2">
                <input
                  type="radio"
                  name="portal-language"
                  value={l.value}
                  checked={account.language === l.value}
                  onChange={() => void chooseLanguage(l.value)}
                  className="size-5"
                />
                {l.label}
              </label>
            ))}
          </div>
        </fieldset>
      </PortalCard>

      <SlotTimesCard onSaved={(text) => setStatus(text)} />

      <PortalCard id="clinics-heading" title={s.account.clinics}>
        {links.status === "loading" && <ScreenLoading label={s.loading} />}
        {links.status === "failed" && <ErrorNotice error={links.error} onRetry={links.retry} />}
        {links.status === "ready" && shown.length === 0 && <p>{s.account.noClinics}</p>}
        <ul className="space-y-4" aria-label={s.account.clinics}>
          {shown.map((link) => (
            <li key={link.id} className="space-y-1 border-t border-slate-200 pt-3 first:border-t-0 first:pt-0">
              <p className="font-semibold">{link.clinic.name}</p>
              <p className="text-sm text-slate-700">
                {link.patient_first_name} · <span className="font-mono">{link.patient_code}</span>
              </p>
              {(link.clinic.address_line !== null || link.clinic.city !== null) && (
                <p className="text-sm text-slate-700">{[link.clinic.address_line, link.clinic.city].filter(Boolean).join(", ")}</p>
              )}
              {link.clinic.phone_e164 !== null && (
                <a href={`tel:${link.clinic.phone_e164}`} className="text-sm font-medium text-brand-800 underline">
                  {link.clinic.phone_e164}
                </a>
              )}
              <p className="text-sm text-slate-700">
                {s.account.linkedHow(
                  link.method === "INVITE" ? s.account.byInvite : s.account.byPrescription,
                  portalDate(link.linked_at, link.clinic.timezone, s),
                )}
              </p>
              {confirming === link.id ? (
                <div className="space-y-2 rounded-lg border border-red-800 bg-red-50 p-3">
                  <p className="font-medium">{s.account.unlinkConfirm(link.clinic.name)}</p>
                  <div className="flex flex-wrap gap-2">
                    <button
                      type="button"
                      onClick={() => void unlink(link)}
                      disabled={busy}
                      className="min-h-11 rounded-lg bg-red-700 px-4 font-semibold text-white hover:bg-red-800"
                    >
                      {s.account.unlinkYes}
                    </button>
                    <button
                      type="button"
                      onClick={() => setConfirming(null)}
                      className="min-h-11 rounded-lg border border-slate-400 bg-white px-4 font-medium hover:bg-slate-100"
                    >
                      {s.account.cancel}
                    </button>
                  </div>
                </div>
              ) : (
                <button
                  type="button"
                  onClick={() => setConfirming(link.id)}
                  aria-label={`${s.account.unlink} ${link.clinic.name}`}
                  className="min-h-11 rounded-lg border border-red-800 px-4 font-medium text-red-900 hover:bg-red-50"
                >
                  {s.account.unlink}
                </button>
              )}
            </li>
          ))}
        </ul>
      </PortalCard>

      <Button onClick={() => void signOut()} disabled={busy} className="w-full">
        {busy ? s.account.signingOut : s.account.signOut}
      </Button>
    </div>
  );
}

const SLOT_KEYS = ["morning", "afternoon", "evening", "night"] as const;
type SlotKey = (typeof SLOT_KEYS)[number];

/** M6b-P3 (spec R34): the person's times of day for the medicine plan; never the prescription. */
function SlotTimesCard({ onSaved }: Readonly<{ onSaved: (text: string) => void }>) {
  const { account, s, leave, replaceAccount } = usePortal();
  const [times, setTimes] = useState<Record<SlotKey, string>>({ ...account.slot_times });
  const [problem, setProblem] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);

  async function save() {
    const values = SLOT_KEYS.map((k) => times[k]);
    const inOrder = values.every((v, i) => /^\d\d:\d\d$/.test(v) && v >= "05:00" && v <= "23:30" && (i === 0 || (values[i - 1] as string) < v));
    setProblem(!inOrder);
    if (!inOrder || busy) return;
    setBusy(true);
    setError(null);
    try {
      const { data } = await portalPatch("/api/v1/portal/me", { slot_times: times });
      replaceAccount(data.account);
      onSaved(s.account.timesSaved);
    } catch (failure) {
      if (!leave(failure)) setError(failure);
    } finally {
      setBusy(false);
    }
  }

  return (
    <PortalCard id="times-heading" title={s.account.times}>
      <p className="text-sm text-slate-700" id="times-help">
        {s.account.timesHelp}
      </p>
      <div className="grid grid-cols-2 gap-3">
        {SLOT_KEYS.map((k) => (
          <div key={k}>
            <label htmlFor={`slot-time-${k}`} className="block font-medium">
              {s.account.slots[k]}
            </label>
            <input
              id={`slot-time-${k}`}
              type="time"
              min="05:00"
              max="23:30"
              step={60}
              value={times[k]}
              aria-describedby={problem ? "times-help times-problem" : "times-help"}
              {...(problem ? { "aria-invalid": true } : {})}
              onChange={(e) => setTimes((old) => ({ ...old, [k]: e.target.value }))}
              className="min-h-11 w-full rounded-lg border border-slate-400 px-2"
            />
          </div>
        ))}
      </div>
      {problem && (
        <p id="times-problem" role="alert" className="text-sm font-medium text-red-900">
          {s.account.timesOrder}
        </p>
      )}
      {error !== null && <ErrorNotice error={error} />}
      <Button size="sm" onClick={() => void save()} disabled={busy}>
        {s.account.saveTimes}
      </Button>
    </PortalCard>
  );
}

/** Until the email is confirmed (M6a-P4, ADR-0016 decision 6); needed to link by prescription. */
export function VerifyBanner() {
  const { s } = usePortal();
  const [state, setState] = useState<"idle" | "sending" | "sent">("idle");
  const [error, setError] = useState<unknown>(null);

  async function resend() {
    setState("sending");
    setError(null);
    try {
      await portalPost("/api/v1/portal/auth/verify-email/resend", undefined);
      setState("sent");
    } catch (failure) {
      setError(failure);
      setState("idle");
    }
  }

  return (
    <section aria-labelledby="verify-banner-heading" className="space-y-3 rounded-lg border border-amber-700 bg-amber-50 p-4 text-amber-950">
      <h2 id="verify-banner-heading" className="font-semibold">
        {s.account.confirmEmail}
      </h2>
      <p>{s.account.confirmEmailHelp}</p>
      {state === "sent" ? (
        <p role="status">{s.account.sent}</p>
      ) : (
        <Button size="sm" onClick={() => void resend()} disabled={state === "sending"}>
          {state === "sending" ? s.account.sending : s.account.resend}
        </Button>
      )}
      {error !== null && <ErrorNotice error={error} />}
    </section>
  );
}
