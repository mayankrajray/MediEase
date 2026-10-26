"use client";

import Link from "next/link";

import { ErrorNotice } from "@/features/auth/ErrorNotice";
import { portalGet } from "@/lib/auth/portal-session";
import { portalDate } from "@/lib/i18n/portal";

import {
  DEFAULT_ZONE,
  type PortalAppointmentGroup,
  type PortalLink,
  type PortalPrescription,
  type PortalReminder,
  usePortalLoad,
  zonesOf,
} from "./data";
import { VerifyBanner } from "./PortalAccountPage";
import { PortalCard, ScreenLoading, usePortal } from "./PortalShell";
import { AppointmentRow, ReminderRow } from "./Rows";

interface HomeData {
  readonly links: readonly PortalLink[];
  readonly groups: readonly PortalAppointmentGroup[];
  readonly prescriptions: readonly PortalPrescription[];
  readonly reminders: readonly PortalReminder[];
  /** When it was read: "upcoming" is decided against this, not during render. */
  readonly now: number;
}

async function loadHome(): Promise<HomeData> {
  const links = (await portalGet("/api/v1/portal/links")).data.items;
  if (links.length === 0) return { links, groups: [], prescriptions: [], reminders: [], now: Date.now() };
  const [groups, prescriptions, reminders] = await Promise.all([
    portalGet("/api/v1/portal/appointments"),
    portalGet("/api/v1/portal/prescriptions"),
    portalGet("/api/v1/portal/reminders"),
  ]);
  return {
    links,
    groups: groups.data.items,
    prescriptions: prescriptions.data.items,
    reminders: reminders.data.items,
    now: Date.now(),
  };
}

const PRIMARY =
  "inline-flex min-h-12 items-center justify-center rounded-lg bg-brand-700 px-5 font-semibold text-white hover:bg-brand-800";
const SECONDARY = "inline-flex min-h-11 items-center font-medium text-brand-800 underline";

/**
 * *Home* (M6b-P2; FR-PRT-05, spec R16, R17): the fresh dashboard with *Find a doctor* when nothing
 * is linked; else the next appointment, the latest prescription and what is coming up.
 */
export function Home() {
  const { account, s } = usePortal();
  const home = usePortalLoad(loadHome);

  return (
    <div className="space-y-5">
      <h1 className="text-2xl font-bold tracking-tight">{s.home.hello(account.full_name)}</h1>
      {!account.email_verified && account.sign_in_method === "PASSWORD" && <VerifyBanner />}
      {home.status === "loading" && <ScreenLoading label={s.loading} />}
      {home.status === "failed" && <ErrorNotice error={home.error} onRetry={home.retry} />}
      {home.status === "ready" && (home.data.links.length === 0 ? <Fresh /> : <Overview data={home.data} />)}
      {home.status === "ready" && (
        <PortalCard id="assistant-heading" title={s.assistant.title}>
          <p className="text-slate-800">{s.assistant.openHelp}</p>
          <Link href="/portal/assistant" className={SECONDARY}>
            {s.assistant.open}
          </Link>
        </PortalCard>
      )}
    </div>
  );
}

function Fresh() {
  const { s } = usePortal();
  return (
    <>
      <PortalCard id="fresh-heading" title={s.home.noAppointments}>
        <p className="text-slate-800">{s.home.freshHelp}</p>
        <Link href="/portal/find" className={PRIMARY}>
          {s.home.findDoctor}
        </Link>
      </PortalCard>
      <details className="rounded-card border border-slate-200 bg-white p-4 shadow-card">
        <summary className="min-h-11 cursor-pointer content-center font-semibold">{s.home.haveInvitation}</summary>
        <p className="mt-2 text-slate-800">{s.home.howToLink}</p>
      </details>
    </>
  );
}

function Overview({ data }: Readonly<{ data: HomeData }>) {
  const { s } = usePortal();
  const { now } = data;
  const zones = zonesOf(data.links);
  const upcoming = data.groups
    .flatMap((g) => g.appointments.map((a) => ({ a, group: g })))
    .filter(({ a }) => Date.parse(a.session_ends_at) > now)
    .sort((x, y) => Date.parse(x.a.starts_at) - Date.parse(y.a.starts_at));
  const next = upcoming[0];
  const latest = data.prescriptions[0];
  const coming = data.reminders.filter((r) => r.status === "SCHEDULED" && Date.parse(r.due_at) >= now).slice(0, 3);

  return (
    <>
      <PortalCard id="next-heading" title={s.home.nextAppointment}>
        {next === undefined ? (
          <p>{s.home.noUpcoming}</p>
        ) : (
          <>
            <p className="font-semibold">{next.group.clinic_name}</p>
            <ul>
              <AppointmentRow a={next.a} zone={next.group.timezone} s={s} />
            </ul>
          </>
        )}
        <Link href="/portal/appointments" className={SECONDARY}>
          {s.home.seeAll}
        </Link>
      </PortalCard>

      {latest !== undefined && (
        <PortalCard id="latest-heading" title={s.home.latestPrescription}>
          <p>
            <span className="font-semibold">{latest.clinic_name}</span> · {latest.doctor_name}
          </p>
          <p className="text-sm text-slate-700">
            {s.prescriptions.issued(portalDate(latest.issued_at, zones.get(latest.clinic_id) ?? DEFAULT_ZONE, s))}
          </p>
          <Link href={`/portal/prescriptions/${latest.id}`} className={SECONDARY}>
            {s.prescriptions.open}
          </Link>
        </PortalCard>
      )}

      {coming.length > 0 && (
        <PortalCard id="coming-heading" title={s.home.upcomingReminders}>
          <ul>
            {coming.map((r) => (
              <ReminderRow key={r.id} r={r} zone={zones.get(r.clinic_id) ?? DEFAULT_ZONE} s={s} />
            ))}
          </ul>
        </PortalCard>
      )}

      <Link href="/portal/find" className={SECONDARY}>
        {s.home.findDoctor}
      </Link>
    </>
  );
}
