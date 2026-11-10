"use client";

import { CalendarDays, Clock, Info, Languages, Link2, MapPin, Navigation, Phone, Share2, TriangleAlert } from "lucide-react";
import Link from "next/link";
import { useCallback, useEffect, useState, useSyncExternalStore } from "react";

import { Avatar } from "@/components/ui/Avatar";
import { Logo } from "@/components/ui/Logo";
import { Skeleton } from "@/components/ui/Skeleton";
import { apiGet, type GetResponse } from "@/lib/api/client";
import { rupees } from "@/lib/format/money";
import { bookingWords, type BookingWords } from "@/lib/i18n/booking-request";
import { portalDay, portalStrings, portalTime, type PortalLanguage } from "@/lib/i18n/portal";

type Clinic = GetResponse<"/api/v1/public/clinics/{slug}">;
type Doctor = Clinic["doctors"][number];
type Days = GetResponse<"/api/v1/public/clinics/{slug}/availability">["days"];
type Session = Days[number]["sessions"][number];

/** One answer, tagged with the doctor and attempt it is for; any other tag means "still loading". */
type Result = { readonly key: string; readonly days: Days | undefined };

const noSubscribe = () => () => undefined;
const canShareNow = () => typeof navigator.share === "function";
const cannotShareOnServer = () => false;

/** The portal form's address for one chosen time; sign-in returns to it unchanged (spec R10).
 * M6c-P7 (discovery R13): a page opened from search keeps `via=directory`. */
export function requestHref(slug: string, doctorId: string, session: Session, slotStart: string | null, lang: PortalLanguage, viaDirectory = false): string {
  const query = new URLSearchParams({ clinic: slug, doctor: doctorId, session: session.starts_at });
  if (slotStart !== null) query.set("slot", slotStart);
  if (lang === "hi") query.set("lang", "hi");
  if (viaDirectory) query.set("via", "directory");
  return `/portal/request?${query.toString()}`;
}

function hoursText(doctor: Doctor, words: BookingWords): string {
  const byDay = new Map<number, string[]>();
  for (const h of doctor.hours) byDay.set(h.weekday, [...(byDay.get(h.weekday) ?? []), `${h.start}–${h.end}`]);
  return [...byDay.entries()]
    .sort(([a], [b]) => a - b)
    .map(([day, spans]) => `${words.page.weekdays[day] ?? ""} ${spans.join(", ")}`)
    .join(" · ");
}

/**
 * The public clinic page (M6b-P4; FR-PUB-01, 04): the clinic, its doctors and the times a patient
 * may ask for in the next 14 days. The words and the clinic's published details only; no medical
 * advice, and an emergency notice above everything else (NFR-19). M6c-P5 (FR-DIS-03): the
 * specialties, each doctor's languages and fee, and a doctor's own profile (`profileOf`: the same
 * page for that doctor alone, its times shown at once).
 */
export function PublicClinicPage({
  clinic,
  language,
  profileOf,
  viaDirectory = false,
}: Readonly<{ clinic: Clinic; language: PortalLanguage; profileOf?: string; viaDirectory?: boolean }>) {
  const words = bookingWords(language);
  const doctors = profileOf === undefined ? clinic.doctors : clinic.doctors.filter((d) => d.id === profileOf);
  const [doctorId, setDoctorId] = useState<string | undefined>(doctors.length === 1 ? doctors[0]?.id : undefined);
  const [result, setResult] = useState<Result | null>(null);
  const [attempt, setAttempt] = useState(0);
  const [copied, setCopied] = useState(false);
  const canShare = useSyncExternalStore(noSubscribe, canShareNow, cannotShareOnServer);
  const other = language === "hi" ? "en" : "hi";

  const key = `${doctorId ?? ""}|${attempt}`;
  useEffect(() => {
    if (doctorId === undefined) return;
    let cancelled = false;
    apiGet("/api/v1/public/clinics/{slug}/availability", {
      pathParams: { slug: clinic.slug },
      query: viaDirectory ? { doctor_id: doctorId, via: "directory" } : { doctor_id: doctorId },
    }).then(
      ({ data }) => {
        if (!cancelled) setResult({ key, days: data.days });
      },
      () => {
        if (!cancelled) setResult({ key, days: undefined });
      },
    );
    return () => {
      cancelled = true;
    };
  }, [clinic.slug, doctorId, key, viaDirectory]);
  const load =
    result === null || result.key !== key
      ? { status: "loading" as const }
      : result.days === undefined
        ? { status: "failed" as const }
        : { status: "ready" as const, days: result.days };

  const retry = useCallback(() => setAttempt((n) => n + 1), []);
  const doctor = doctors.find((d) => d.id === doctorId);
  const address = [clinic.address_line, clinic.city, clinic.state, clinic.pincode].filter((p) => p !== null && p !== "").join(", ");

  async function copy() {
    try {
      await navigator.clipboard.writeText(window.location.href.split("?")[0] ?? window.location.href);
      setCopied(true);
    } catch {
      setCopied(false);
    }
  }

  async function share() {
    try {
      await navigator.share({ title: clinic.name, url: window.location.href.split("?")[0] ?? window.location.href });
    } catch {
      // Dismissed by the person: nothing to do.
    }
  }

  // M7c-P7 (M6): choosing a doctor brings their times into view (on a phone they sit below every
  // doctor card); with reduced motion it jumps.
  function chooseDoctor(id: string) {
    setDoctorId(id);
    window.requestAnimationFrame(() => {
      const reduce = typeof window.matchMedia === "function" && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
      document.getElementById("times-heading")?.scrollIntoView?.({ behavior: reduce ? "auto" : "smooth", block: "start" });
    });
  }

  const button =
    "inline-flex min-h-11 cursor-pointer items-center justify-center gap-2 rounded-lg border border-slate-300 bg-surface px-3 text-sm font-semibold text-slate-900 transition-colors hover:border-brand-300 hover:bg-brand-50";

  return (
    <div lang={language} className="min-h-screen bg-canvas">
      <header className="sticky top-0 z-20 border-b border-line bg-surface/95 backdrop-blur supports-[backdrop-filter]:bg-surface/85">
        <div className="mx-auto flex max-w-3xl items-center justify-between gap-3 px-4 py-2">
          <Link href={language === "hi" ? "/?lang=hi" : "/"} className="flex min-h-11 items-center">
            <Logo />
          </Link>
          <Link
            href={`/c/${encodeURIComponent(clinic.slug)}${profileOf === undefined ? "" : `/doctors/${encodeURIComponent(profileOf)}`}?lang=${other}`}
            lang={other}
            aria-label={words.switchLabel}
            className={button}
          >
            <Languages aria-hidden="true" className="size-4" />
            {words.switchTo}
          </Link>
        </div>
      </header>
      <main className="mx-auto max-w-3xl space-y-5 px-4 pb-10 pt-5">
        <p role="note" className="flex gap-2 rounded-xl border border-warning-line bg-warning-soft p-3 text-sm text-slate-900">
          <TriangleAlert aria-hidden="true" className="mt-0.5 size-4 shrink-0 text-warning" />
          <span>{words.page.emergency}</span>
        </p>

        <section aria-labelledby="clinic-name" className="space-y-3 rounded-card border border-line bg-surface p-4 shadow-card sm:p-5">
          <h1 id="clinic-name" className="heading-4 break-words text-slate-900">
            {clinic.name}
          </h1>
          {address !== "" && (
            <p className="flex gap-2 text-slate-800">
              <MapPin aria-hidden="true" className="mt-0.5 size-4 shrink-0 text-slate-500" />
              <span className="min-w-0 break-words">{address}</span>
            </p>
          )}
          {clinic.specialties.length > 0 && (
            <p className="text-sm text-slate-800">
              {words.page.specialties}: {clinic.specialties.join(", ")}
            </p>
          )}
          <div className="grid grid-cols-2 gap-2 sm:flex sm:flex-wrap">
            {clinic.phone_e164 !== null && (
              <a href={`tel:${clinic.phone_e164}`} className={button}>
                <Phone aria-hidden="true" className="size-4" />
                {words.page.call}
              </a>
            )}
            {clinic.map_url !== null && (
              <a href={clinic.map_url} target="_blank" rel="noopener noreferrer" className={button}>
                <Navigation aria-hidden="true" className="size-4" />
                {words.page.directions}
              </a>
            )}
            {canShare && (
              <button type="button" onClick={() => void share()} className={button}>
                <Share2 aria-hidden="true" className="size-4" />
                {words.page.share}
              </button>
            )}
            <button type="button" onClick={() => void copy()} className={button}>
              <Link2 aria-hidden="true" className="size-4" />
              {words.page.copy}
            </button>
          </div>
          <p role="status" aria-live="polite" className={copied ? "text-sm font-medium text-success" : "sr-only"}>
            {copied ? words.page.copied : ""}
          </p>
          <p className="flex gap-2 rounded-lg bg-surface-muted p-3 text-sm text-slate-700">
            <Info aria-hidden="true" className="mt-0.5 size-4 shrink-0 text-info" />
            <span>{words.page.howItWorks}</span>
          </p>
        </section>

        <section aria-labelledby="doctors-heading" className="space-y-3">
          <div className="flex flex-wrap items-baseline justify-between gap-2">
            <h2 id="doctors-heading" className="heading-6 text-slate-900">
              {words.page.doctors}
            </h2>
            {profileOf !== undefined && (
              <Link
                href={`/c/${encodeURIComponent(clinic.slug)}${language === "hi" ? "?lang=hi" : ""}`}
                className="inline-flex min-h-11 items-center text-sm font-semibold text-brand-800 underline underline-offset-2"
              >
                {words.page.allDoctors}
              </Link>
            )}
          </div>
          {doctorId === undefined && <p className="text-slate-700">{words.page.pickDoctor}</p>}
          <ul className="space-y-3">
            {doctors.map((d) => {
              const chosen = d.id === doctorId;
              const hours = hoursText(d, words);
              const about = [d.qualification, d.specialty].filter((p) => p !== null && p !== "").join(" · ");
              return (
                <li
                  key={d.id}
                  className={`space-y-3 rounded-card border bg-surface p-4 shadow-card transition-colors sm:p-5 ${chosen ? "border-brand-300 ring-1 ring-brand-200" : "border-line"}`}
                >
                  <div className="flex items-start gap-3">
                    <Avatar name={d.display_name} />
                    <div className="min-w-0 flex-1">
                      <p className="break-words font-semibold text-slate-900">{d.display_name}</p>
                      {about !== "" && <p className="text-sm text-slate-800">{about}</p>}
                    </div>
                  </div>
                  {d.fee_paise !== null && (
                    <p className="inline-flex rounded-md bg-surface-muted px-2 py-1 text-sm font-semibold tabular-nums text-slate-800">
                      {words.page.fee(rupees(d.fee_paise))}
                    </p>
                  )}
                  {(hours !== "" || d.languages.length > 0) && (
                    <div className="space-y-1 text-sm text-slate-700">
                      {hours !== "" && (
                        <p className="flex gap-2">
                          <Clock aria-hidden="true" className="mt-0.5 size-4 shrink-0 text-slate-500" />
                          <span className="min-w-0">
                            {words.page.hours}: {hours}
                          </span>
                        </p>
                      )}
                      {d.languages.length > 0 && (
                        <p className="flex gap-2">
                          <Languages aria-hidden="true" className="mt-0.5 size-4 shrink-0 text-slate-500" />
                          <span className="min-w-0">
                            {words.page.languages}: {d.languages.join(", ")}
                          </span>
                        </p>
                      )}
                    </div>
                  )}
                  <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
                    <button
                      type="button"
                      aria-pressed={chosen}
                      onClick={() => chooseDoctor(d.id)}
                      className={`inline-flex min-h-11 cursor-pointer items-center justify-center gap-2 rounded-lg px-4 font-semibold transition-colors max-sm:w-full ${chosen ? "bg-brand-800 text-white" : "bg-brand-700 text-white hover:bg-brand-800"}`}
                    >
                      <CalendarDays aria-hidden="true" className="size-4" />
                      {words.page.seeTimes}
                    </button>
                    {profileOf === undefined && (
                      <Link
                        href={`/c/${encodeURIComponent(clinic.slug)}/doctors/${encodeURIComponent(d.id)}${language === "hi" ? "?lang=hi" : ""}`}
                        className="inline-flex min-h-11 items-center text-sm font-semibold text-brand-800 underline underline-offset-2"
                      >
                        {words.page.profile}
                        <span className="sr-only">: {d.display_name}</span>
                      </Link>
                    )}
                  </div>
                </li>
              );
            })}
          </ul>
        </section>

        {doctor !== undefined && (
          <section aria-labelledby="times-heading" className="scroll-mt-20 space-y-3">
            <h2 id="times-heading" className="heading-6 break-words text-slate-900">
              {words.page.timesFor(doctor.display_name)}
            </h2>
            {load.status === "loading" && (
              <div>
                <p role="status" className="sr-only">
                  {words.page.loading}
                </p>
                <div aria-hidden="true" className="space-y-3">
                  <Skeleton className="h-32" />
                  <Skeleton className="h-32" />
                </div>
              </div>
            )}
            {load.status === "failed" && (
              <div role="alert" className="space-y-3 rounded-xl border border-danger-line bg-danger-soft p-4 text-slate-900">
                <p className="font-semibold">{words.page.failed}</p>
                <button type="button" onClick={retry} className={button}>
                  {words.page.retry}
                </button>
              </div>
            )}
            {load.status === "ready" && load.days.length === 0 && (
              <p className="rounded-card border border-dashed border-slate-300 bg-surface px-4 py-8 text-center text-slate-700">{words.page.none}</p>
            )}
            {load.status === "ready" && load.days.length > 1 && (
              <nav aria-label={words.page.jumpTo} className="rounded-card border border-line bg-surface p-3 shadow-card">
                <p className="mb-2 text-sm font-semibold text-slate-900">{words.page.jumpTo}</p>
                <ul className="grid grid-cols-4 gap-2 sm:grid-cols-7">
                  {load.days.map((day) => {
                    const at = day.sessions[0]?.starts_at;
                    return at === undefined ? null : (
                      <li key={day.date}>
                        <a
                          href={`#day-${day.date}`}
                          className="flex min-h-11 flex-col items-center justify-center rounded-lg border border-line px-1 py-1 text-center text-xs font-semibold leading-tight text-slate-800 transition-colors hover:border-brand-300 hover:bg-brand-50"
                        >
                          {portalDay(at, clinic.timezone, portalStrings(language))}
                        </a>
                      </li>
                    );
                  })}
                </ul>
              </nav>
            )}
            {load.status === "ready" &&
              load.days.map((day) => (
                <DayOffers key={day.date} day={day} clinic={clinic} doctor={doctor} words={words} language={language} viaDirectory={viaDirectory} />
              ))}
          </section>
        )}
      </main>
    </div>
  );
}

function DayOffers({
  day,
  clinic,
  doctor,
  words,
  language,
  viaDirectory,
}: Readonly<{ day: Days[number]; clinic: Clinic; doctor: Doctor; words: BookingWords; language: PortalLanguage; viaDirectory: boolean }>) {
  const s = portalStrings(language);
  const first = day.sessions[0];
  if (first === undefined) return null;
  const chip =
    "inline-flex min-h-11 w-full items-center justify-center rounded-lg border border-brand-300 bg-brand-50 px-2 text-sm font-semibold tabular-nums text-brand-900 transition-colors hover:border-brand-700 hover:bg-brand-100";
  // M7c-P7 (M6): one compact row per session (time and places, then a short Ask), so a phone
  // shows a fortnight in a few screens; slot sessions keep a grid of times.
  return (
    <div id={`day-${day.date}`} className="scroll-mt-20 rounded-card border border-line bg-surface shadow-card">
      <h3 className="border-b border-line px-4 py-3 font-semibold text-slate-900">{portalDay(first.starts_at, clinic.timezone, s)}</h3>
      <ul className="divide-y divide-line">
        {day.sessions.map((session) => {
          const span = words.page.session(portalTime(session.starts_at, clinic.timezone, s), portalTime(session.ends_at, clinic.timezone, s));
          return (
            <li key={session.starts_at} className="space-y-2 px-4 py-3">
              {session.mode === "TOKENS" ? (
                <div className="flex items-center gap-3">
                  <p className="min-w-0 flex-1 text-sm text-slate-700">
                    <span className="block tabular-nums text-slate-900">{span}</span>
                    <span className="block font-medium text-slate-700">{words.page.placesLeft(session.places_left)}</span>
                  </p>
                  <Link
                    href={requestHref(clinic.slug, doctor.id, session, null, language, viaDirectory)}
                    aria-label={words.page.requestSession}
                    className="inline-flex min-h-11 min-w-20 shrink-0 items-center justify-center rounded-lg bg-brand-700 px-4 font-semibold text-white transition-colors hover:bg-brand-800"
                  >
                    {words.page.ask}
                  </Link>
                </div>
              ) : (
                <>
                  <p className="text-sm tabular-nums text-slate-700">{span}</p>
                  <ul className="grid grid-cols-3 gap-2 sm:grid-cols-5">
                    {session.slots.map((slot) => (
                      <li key={slot.starts_at}>
                        <Link
                          href={requestHref(clinic.slug, doctor.id, session, slot.starts_at, language, viaDirectory)}
                          aria-label={words.page.requestSlot(portalTime(slot.starts_at, clinic.timezone, s))}
                          className={chip}
                        >
                          {portalTime(slot.starts_at, clinic.timezone, s)}
                        </Link>
                      </li>
                    ))}
                  </ul>
                </>
              )}
            </li>
          );
        })}
      </ul>
    </div>
  );
}