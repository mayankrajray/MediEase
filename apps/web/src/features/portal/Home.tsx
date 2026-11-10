"use client";

import { BellRing, Bot, Building2, CalendarDays, ChevronRight, FileText, MailQuestion, Search } from "lucide-react";
import Link from "next/link";
import type { ReactNode } from "react";

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
import { PORTAL_LINK, PortalCard, PortalTitle, ScreenLoading, usePortal } from "./PortalShell";
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
  "inline-flex min-h-12 w-full items-center justify-center gap-2 rounded-lg bg-brand-700 px-5 font-semibold text-white shadow-sm transition-colors duration-200 ease-brand hover:bg-brand-800 motion-reduce:transition-none sm:w-auto";

/** A whole-card link to another part of the portal: icon, title, one line, chevron; its visible words name it. */
function ActionTile({ href, title, help, icon }: Readonly<{ href: string; title: string; help: string; icon: ReactNode }>) {
  return (
    <Link
      href={href}
      prefetch={false}
      className="group flex min-h-16 items-center gap-3 rounded-card border border-line bg-white p-4 shadow-card transition duration-200 ease-brand hover:border-brand-300 hover:shadow-md motion-reduce:transition-none"
    >
      <span aria-hidden="true" className="grid size-10 shrink-0 place-items-center rounded-full bg-brand-50 text-brand-700 [&>svg]:size-5">
        {icon}
      </span>
      <span className="min-w-0 flex-1">
        <span className="block font-semibold text-slate-900">
          {title}
        </span>
        <span className="block text-sm text-slate-700">
          {help}
        </span>
      </span>
      <ChevronRight aria-hidden="true" className="size-5 shrink-0 text-slate-500 transition-transform duration-200 group-hover:translate-x-0.5 motion-reduce:transition-none" />
    </Link>
  );
}

/**
 * *Home* (M6b-P2; FR-PRT-05, spec R16, R17): the fresh dashboard with *Find a doctor* when nothing
 * is linked; else the next appointment, the latest prescription and what is coming up.
 * M7c-P7 (M7): the next appointment leads as the one highlighted card, each card has its icon and
 * its link at the heading's end, and *Find a doctor* and the assistant are whole-card links.
 */
export function Home() {
  const { account, s } = usePortal();
  const home = usePortalLoad(loadHome);
  const linked = home.status === "ready" && home.data.links.length > 0;

  return (
    <div className="space-y-5">
      <PortalTitle>{s.home.hello(account.full_name)}</PortalTitle>
      {!account.email_verified && account.sign_in_method === "PASSWORD" && <VerifyBanner />}
      {home.status === "loading" && <ScreenLoading label={s.loading} />}
      {home.status === "failed" && <ErrorNotice error={home.error} onRetry={home.retry} />}
      {home.status === "ready" && (linked ? <Overview data={home.data} /> : <Fresh />)}
      {home.status === "ready" && (
        <div className={linked ? "grid gap-3 sm:grid-cols-2 sm:items-start" : ""}>
          {linked && <ActionTile href="/portal/find" title={s.home.findDoctor} help={s.home.findHelp} icon={<Search />} />}
          <PortalCard id="assistant-heading" title={s.assistant.title} icon={<Bot />}>
            <p className="text-slate-800">{s.assistant.openHelp}</p>
            <Link href="/portal/assistant" prefetch={false} className={PORTAL_LINK}>
              {s.assistant.open}
              <ChevronRight aria-hidden="true" className="size-4" />
            </Link>
          </PortalCard>
        </div>
      )}
    </div>
  );
}

function Fresh() {
  const { s } = usePortal();
  return (
    <>
      <PortalCard id="fresh-heading" title={s.home.noAppointments} icon={<CalendarDays />} highlight>
        <p className="text-slate-800">{s.home.freshHelp}</p>
        <Link href="/portal/find" prefetch={false} className={PRIMARY}>
          <Search aria-hidden="true" className="size-5" />
          {s.home.findDoctor}
        </Link>
      </PortalCard>
      <details className="group rounded-card border border-line bg-white shadow-card">
        <summary className="flex min-h-14 cursor-pointer list-none items-center gap-3 px-4 font-semibold text-slate-900 [&::-webkit-details-marker]:hidden">
          <MailQuestion aria-hidden="true" className="size-5 shrink-0 text-brand-700" />
          <span className="flex-1">{s.home.haveInvitation}</span>
          <ChevronRight aria-hidden="true" className="size-5 shrink-0 text-slate-500 transition-transform duration-200 group-open:rotate-90 motion-reduce:transition-none" />
        </summary>
        <p className="px-4 pb-4 text-slate-800">{s.home.howToLink}</p>
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
      <PortalCard
        id="next-heading"
        title={s.home.nextAppointment}
        icon={<CalendarDays />}
        highlight
        action={
          <Link href="/portal/appointments" prefetch={false} className={PORTAL_LINK}>
            {s.home.seeAll}
            <ChevronRight aria-hidden="true" className="size-4" />
          </Link>
        }
      >
        {next === undefined ? (
          <p className="text-slate-700">{s.home.noUpcoming}</p>
        ) : (
          <>
            <p className="flex items-center gap-1.5 font-semibold text-slate-800">
              <Building2 aria-hidden="true" className="size-4 shrink-0 text-slate-500" />
              <span className="min-w-0 [overflow-wrap:anywhere]">{next.group.clinic_name}</span>
            </p>
            <ul>
              <AppointmentRow a={next.a} zone={next.group.timezone} s={s} />
            </ul>
          </>
        )}
      </PortalCard>

      {latest !== undefined && (
        <PortalCard id="latest-heading" title={s.home.latestPrescription} icon={<FileText />}>
          <div className="flex flex-wrap items-end justify-between gap-x-4 gap-y-1">
            <div className="min-w-0">
              <p className="[overflow-wrap:anywhere]">
                <span className="font-semibold">{latest.clinic_name}</span> · {latest.doctor_name}
              </p>
              <p className="text-sm text-slate-700">
                {s.prescriptions.issued(portalDate(latest.issued_at, zones.get(latest.clinic_id) ?? DEFAULT_ZONE, s))}
              </p>
            </div>
            <Link href={`/portal/prescriptions/${latest.id}`} prefetch={false} className={PORTAL_LINK}>
              {s.prescriptions.open}
              <ChevronRight aria-hidden="true" className="size-4" />
            </Link>
          </div>
        </PortalCard>
      )}

      {coming.length > 0 && (
        <PortalCard id="coming-heading" title={s.home.upcomingReminders} icon={<BellRing />}>
          <ul>
            {coming.map((r) => (
              <ReminderRow key={r.id} r={r} zone={zones.get(r.clinic_id) ?? DEFAULT_ZONE} s={s} />
            ))}
          </ul>
        </PortalCard>
      )}
    </>
  );
}
