"use client";

import dynamic from "next/dynamic";
import { useRouter } from "next/navigation";
import { useState } from "react";

import { Bell, Building2, Clock, KeyRound, Languages, LogOut, Mail, MailWarning, MapPin, Phone, Unlink } from "lucide-react";

import { initials } from "@/components/ui/Avatar";
import { Button } from "@/components/ui/Button";
import { CHOICE_CARD, CHOICE_INPUT, INPUT, LABEL } from "@/components/ui/Field";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { ErrorNotice } from "@/features/auth/ErrorNotice";
import { AppPromptsGate } from "@/features/pwa/AppPromptsGate";
import { PORTAL_SIGN_IN_PATH, portalDelete, portalGet, portalPatch, portalPost, portalPut } from "@/lib/auth/portal-session";
import { notificationWords } from "@/lib/i18n/patient-notifications";
import { type PortalLanguage, portalDate } from "@/lib/i18n/portal";

import { type PortalLink, type PortalNotificationPreference, usePortalLoad } from "./data";
import { PortalCard, PortalTitle, ScreenLoading, usePortal } from "./PortalShell";

// M7e-E5: the pop-up alerts card is loaded when this page renders, not with every page that links here.
const PortalDevicePush = dynamic(() => import("./PortalDevicePush").then((m) => m.PortalDevicePush), { ssr: false });

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
      <PortalTitle>{s.account.title}</PortalTitle>
      <AppPromptsGate language={s.lang} />
      {error !== null && <ErrorNotice error={error} />}
      <p role="status" className="min-h-0 font-medium text-success empty:sr-only">
        {status}
      </p>

      <PortalCard id="profile-heading" title={account.full_name} icon={<span className="text-sm font-bold">{initials(account.full_name)}</span>} highlight>
        <dl className="grid gap-3 sm:grid-cols-[auto_1fr] sm:gap-x-6">
          <dt className="flex items-center gap-2 text-sm font-semibold text-slate-700">
            <Mail aria-hidden="true" className="size-4 shrink-0" />
            {s.account.email}
          </dt>
          <dd className="-mt-2 flex flex-wrap items-center gap-x-2 gap-y-1 sm:mt-0">
            <span className="break-all text-slate-900">{account.email}</span>
            <StatusBadge tone={account.email_verified ? "done" : "waiting"}>{account.email_verified ? s.account.verified : s.account.notVerified}</StatusBadge>
          </dd>
          <dt className="flex items-center gap-2 text-sm font-semibold text-slate-700">
            <KeyRound aria-hidden="true" className="size-4 shrink-0" />
            {s.account.signsInWith}
          </dt>
          <dd className="-mt-2 text-slate-900 sm:mt-0">{account.sign_in_method === "GOOGLE" ? s.account.google : s.account.password}</dd>
        </dl>
        {!account.email_verified && account.sign_in_method === "PASSWORD" && <VerifyBanner />}
      </PortalCard>

      <PortalCard id="language-heading" title={s.account.language} icon={<Languages />}>
        <fieldset>
          <legend className="sr-only">{s.account.language}</legend>
          <div className="grid grid-cols-2 gap-2 sm:max-w-sm">
            {LANGUAGES.map((l) => (
              <label key={l.value} lang={l.value} className={`${CHOICE_CARD} min-h-11 font-medium`}>
                <input
                  type="radio"
                  name="portal-language"
                  value={l.value}
                  checked={account.language === l.value}
                  onChange={() => void chooseLanguage(l.value)}
                  className={CHOICE_INPUT}
                />
                {l.label}
              </label>
            ))}
          </div>
        </fieldset>
      </PortalCard>

      <SlotTimesCard onSaved={(text) => setStatus(text)} />

      <PortalDevicePush onSaved={setStatus} />

      <NotificationSwitches onSaved={(text) => setStatus(text)} />

      <PortalCard id="clinics-heading" title={s.account.clinics} icon={<Building2 />}>
        {links.status === "loading" && <ScreenLoading label={s.loading} />}
        {links.status === "failed" && <ErrorNotice error={links.error} onRetry={links.retry} />}
        {links.status === "ready" && shown.length === 0 && <p>{s.account.noClinics}</p>}
        <ul className="space-y-3" aria-label={s.account.clinics}>
          {shown.map((link) => (
            <li key={link.id} className="space-y-1.5 rounded-lg border border-line p-3">
              <p className="font-semibold text-slate-900 [overflow-wrap:anywhere]">{link.clinic.name}</p>
              <p className="text-sm text-slate-700">
                {link.patient_first_name} · <span className="font-mono">{link.patient_code}</span>
              </p>
              {(link.clinic.address_line !== null || link.clinic.city !== null) && (
                <p className="flex items-start gap-1.5 text-sm text-slate-700">
                  <MapPin aria-hidden="true" className="mt-0.5 size-3.5 shrink-0" />
                  <span className="min-w-0">{[link.clinic.address_line, link.clinic.city].filter(Boolean).join(", ")}</span>
                </p>
              )}
              {link.clinic.phone_e164 !== null && (
                <a href={`tel:${link.clinic.phone_e164}`} className="inline-flex min-h-11 items-center gap-1.5 text-sm font-semibold text-brand-800 underline-offset-4 hover:underline">
                  <Phone aria-hidden="true" className="size-3.5 shrink-0" />
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
                <div className="space-y-3 rounded-lg border border-danger-line bg-danger-soft p-3">
                  <p className="font-medium text-slate-900">{s.account.unlinkConfirm(link.clinic.name)}</p>
                  <div className="grid gap-2 min-[400px]:flex min-[400px]:flex-wrap">
                    <Button variant="danger" onClick={() => void unlink(link)} loading={busy} className="min-h-11">
                      {s.account.unlinkYes}
                    </Button>
                    <Button onClick={() => setConfirming(null)} className="min-h-11">
                      {s.account.cancel}
                    </Button>
                  </div>
                </div>
              ) : (
                <button
                  type="button"
                  onClick={() => setConfirming(link.id)}
                  aria-label={`${s.account.unlink} ${link.clinic.name}`}
                  className="inline-flex min-h-11 items-center gap-1.5 rounded-lg border border-danger-line bg-white px-4 font-semibold text-danger transition-colors duration-200 ease-brand hover:bg-danger-soft motion-reduce:transition-none"
                >
                  <Unlink aria-hidden="true" className="size-4" />
                  {s.account.unlink}
                </button>
              )}
            </li>
          ))}
        </ul>
      </PortalCard>

      <Button size="lg" onClick={() => void signOut()} disabled={busy} icon={<LogOut className="size-5" />} className="w-full">
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
    <PortalCard id="times-heading" title={s.account.times} icon={<Clock />}>
      <p className="text-sm text-slate-700" id="times-help">
        {s.account.timesHelp}
      </p>
      <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
        {SLOT_KEYS.map((k) => (
          <div key={k}>
            <label htmlFor={`slot-time-${k}`} className={LABEL}>
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
              className={`${INPUT} mt-1 min-h-11 tabular-nums`}
            />
          </div>
        ))}
      </div>
      {problem && (
        <p id="times-problem" role="alert" className="text-sm font-medium text-danger">
          {s.account.timesOrder}
        </p>
      )}
      {error !== null && <ErrorNotice error={error} />}
      <Button onClick={() => void save()} loading={busy} className="min-h-11">
        {s.account.saveTimes}
      </Button>
    </PortalCard>
  );
}

async function loadPreferences(): Promise<readonly PortalNotificationPreference[]> {
  return (await portalGet("/api/v1/portal/notification-preferences")).data.items;
}

/**
 * M6b-P6 (spec R62, R63): what the person is told about, in the app and by email. Everything is on
 * until they turn it off; email is offered only for the four answers to a booking request. M7e-E5:
 * and as a pop-up alert on the devices they turned alerts on for (web-push R53).
 */
function NotificationSwitches({ onSaved }: Readonly<{ onSaved: (text: string) => void }>) {
  const { s, leave } = usePortal();
  const words = notificationWords(s.lang);
  const loaded = usePortalLoad(loadPreferences);
  const [items, setItems] = useState<readonly PortalNotificationPreference[] | undefined>(undefined);
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  const shown = items ?? (loaded.status === "ready" ? loaded.data : []);

  async function change(kind: PortalNotificationPreference["kind"], channel: "IN_APP" | "EMAIL" | "PUSH", enabled: boolean) {
    if (busy) return;
    setBusy(true);
    setError(null);
    try {
      const { data } = await portalPut("/api/v1/portal/notification-preferences", { kind, channel, enabled });
      setItems(data.items);
      onSaved(words.switches.saved);
    } catch (failure) {
      if (!leave(failure)) setError(failure);
    } finally {
      setBusy(false);
    }
  }

  return (
    <PortalCard id="notifications-heading" title={words.switches.title} icon={<Bell />}>
      <p className="text-sm text-slate-700">{words.switches.help}</p>
      {loaded.status === "loading" && <ScreenLoading label={s.loading} />}
      {loaded.status === "failed" && <ErrorNotice error={loaded.error} onRetry={loaded.retry} />}
      {error !== null && <ErrorNotice error={error} />}
      <ul className="divide-y divide-line">
        {shown.map((p) => (
          <li key={p.kind} className="py-2 first:pt-0 last:pb-0">
            <fieldset>
              <legend className="py-1 font-medium text-slate-900">{words.switches.kinds[p.kind]}</legend>
              <div className="mt-1 flex flex-wrap gap-2">
                <label className={`${CHOICE_CARD} min-h-11 text-sm font-medium`}>
                  <input
                    type="checkbox"
                    checked={p.in_app}
                    disabled={busy}
                    onChange={(e) => void change(p.kind, "IN_APP", e.target.checked)}
                    className={CHOICE_INPUT}
                  />
                  {words.switches.inApp}
                </label>
                {p.email !== null && (
                  <label className={`${CHOICE_CARD} min-h-11 text-sm font-medium`}>
                    <input
                      type="checkbox"
                      checked={p.email}
                      disabled={busy}
                      onChange={(e) => void change(p.kind, "EMAIL", e.target.checked)}
                      className={CHOICE_INPUT}
                    />
                    {words.switches.email}
                  </label>
                )}
                <label className={`${CHOICE_CARD} min-h-11 text-sm font-medium`}>
                  <input
                    type="checkbox"
                    checked={p.push}
                    disabled={busy}
                    onChange={(e) => void change(p.kind, "PUSH", e.target.checked)}
                    className={CHOICE_INPUT}
                  />
                  {words.switches.push}
                </label>
              </div>
            </fieldset>
          </li>
        ))}
      </ul>
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
    <section aria-labelledby="verify-banner-heading" className="flex gap-3 rounded-card border border-warning-line bg-warning-soft p-4 text-slate-900">
      <MailWarning aria-hidden="true" className="mt-0.5 size-5 shrink-0 text-warning" />
      <div className="min-w-0 flex-1 space-y-3">
        <h2 id="verify-banner-heading" className="font-semibold">
          {s.account.confirmEmail}
        </h2>
        <p className="text-slate-800">{s.account.confirmEmailHelp}</p>
        {state === "sent" ? (
          <p role="status" className="font-medium">
            {s.account.sent}
          </p>
        ) : (
          <Button onClick={() => void resend()} loading={state === "sending"} className="min-h-11">
            {state === "sending" ? s.account.sending : s.account.resend}
          </Button>
        )}
        {error !== null && <ErrorNotice error={error} />}
      </div>
    </section>
  );
}
