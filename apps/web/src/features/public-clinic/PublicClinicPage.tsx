"use client";

import Link from "next/link";
import { useCallback, useEffect, useState, useSyncExternalStore } from "react";

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

  const button = "inline-flex min-h-11 items-center rounded-lg border border-slate-400 bg-white px-3 text-sm font-medium text-slate-900 hover:bg-slate-100";

  return (
    <div lang={language} className="min-h-screen bg-canvas">
      <header className="border-b border-slate-200 bg-white">
        <div className="mx-auto flex max-w-3xl items-center justify-between gap-3 px-4 py-2">
          <span className="flex min-h-11 items-center gap-2 text-lg font-bold text-slate-900">
            <span aria-hidden="true" className="grid size-8 place-items-center rounded-xl bg-brand-700 text-sm text-white">
              M
            </span>
            MediEase
          </span>
          <Link
            href={`/c/${encodeURIComponent(clinic.slug)}${profileOf === undefined ? "" : `/doctors/${encodeURIComponent(profileOf)}`}?lang=${other}`}
            lang={other}
            aria-label={words.switchLabel}
            className={button}
          >
            {words.switchTo}
          </Link>
        </div>
      </header>
      <main className="mx-auto max-w-3xl space-y-5 px-4 py-5">
        <p role="note" className="rounded-lg border border-amber-700 bg-amber-50 p-3 text-sm text-amber-950">
          {words.page.emergency}
        </p>

        <section aria-labelledby="clinic-name" className="space-y-2 rounded-card border border-slate-200 bg-white p-4 shadow-card">
          <h1 id="clinic-name" className="text-2xl font-bold tracking-tight">
            {clinic.name}
          </h1>
          {address !== "" && <p className="text-slate-800">{address}</p>}
          {clinic.specialties.length > 0 && (
            <p className="text-sm text-slate-800">
              {words.page.specialties}: {clinic.specialties.join(", ")}
            </p>
          )}
          <div className="flex flex-wrap gap-2">
            {clinic.phone_e164 !== null && (
              <a href={`tel:${clinic.phone_e164}`} className={button}>
                {words.page.call}
              </a>
            )}
            {clinic.map_url !== null && (
              <a href={clinic.map_url} target="_blank" rel="noopener noreferrer" className={button}>
                {words.page.directions}
              </a>
            )}
            {canShare && (
              <button type="button" onClick={() => void share()} className={button}>
                {words.page.share}
              </button>
            )}
            <button type="button" onClick={() => void copy()} className={button}>
              {words.page.copy}
            </button>
          </div>
          <p role="status" aria-live="polite" className={copied ? "text-sm font-medium text-emerald-900" : "sr-only"}>
            {copied ? words.page.copied : ""}
          </p>
          <p className="text-sm text-slate-700">{words.page.howItWorks}</p>
        </section>

        <section aria-labelledby="doctors-heading" className="space-y-3">
          <h2 id="doctors-heading" className="text-lg font-bold">
            {words.page.doctors}
          </h2>
          {profileOf !== undefined && (
            <Link href={`/c/${encodeURIComponent(clinic.slug)}${language === "hi" ? "?lang=hi" : ""}`} className="font-medium text-brand-800 underline">
              {words.page.allDoctors}
            </Link>
          )}
          {doctorId === undefined && <p>{words.page.pickDoctor}</p>}
          <ul className="space-y-3">
            {doctors.map((d) => {
              const chosen = d.id === doctorId;
              const hours = hoursText(d, words);
              return (
                <li key={d.id} className="space-y-1 rounded-card border border-slate-200 bg-white p-4 shadow-card">
                  <p className="font-semibold">{d.display_name}</p>
                  {(d.qualification !== null || d.specialty !== null) && (
                    <p className="text-sm text-slate-800">{[d.qualification, d.specialty].filter((p) => p !== null && p !== "").join(" · ")}</p>
                  )}
                  {hours !== "" && (
                    <p className="text-sm text-slate-700">
                      {words.page.hours}: {hours}
                    </p>
                  )}
                  {d.languages.length > 0 && (
                    <p className="text-sm text-slate-700">
                      {words.page.languages}: {d.languages.join(", ")}
                    </p>
                  )}
                  {d.fee_paise !== null && <p className="text-sm text-slate-700">{words.page.fee(rupees(d.fee_paise))}</p>}
                  {profileOf === undefined && (
                    <Link
                      href={`/c/${encodeURIComponent(clinic.slug)}/doctors/${encodeURIComponent(d.id)}${language === "hi" ? "?lang=hi" : ""}`}
                      className="mr-2 inline-flex min-h-11 items-center text-sm font-medium text-brand-800 underline"
                    >
                      {words.page.profile}
                      <span className="sr-only">: {d.display_name}</span>
                    </Link>
                  )}
                  <button
                    type="button"
                    aria-pressed={chosen}
                    onClick={() => setDoctorId(d.id)}
                    className={`${button} ${chosen ? "border-brand-700 bg-brand-50 text-brand-900" : ""}`}
                  >
                    {words.page.seeTimes}
                  </button>
                </li>
              );
            })}
          </ul>
        </section>

        {doctor !== undefined && (
          <section aria-labelledby="times-heading" className="space-y-3">
            <h2 id="times-heading" className="text-lg font-bold">
              {words.page.timesFor(doctor.display_name)}
            </h2>
            {load.status === "loading" && (
              <p role="status" className="text-slate-700">
                {words.page.loading}
              </p>
            )}
            {load.status === "failed" && (
              <div role="alert" className="space-y-2 rounded-lg border border-red-700 bg-red-50 p-4 text-red-950">
                <p>{words.page.failed}</p>
                <button type="button" onClick={retry} className={button}>
                  {words.page.retry}
                </button>
              </div>
            )}
            {load.status === "ready" && load.days.length === 0 && <p>{words.page.none}</p>}
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
  const link = "inline-flex min-h-11 items-center rounded-lg border border-brand-700 bg-white px-3 text-sm font-semibold text-brand-900 hover:bg-brand-50";
  return (
    <div className="space-y-2 rounded-card border border-slate-200 bg-white p-4 shadow-card">
      <h3 className="font-semibold">{portalDay(first.starts_at, clinic.timezone, s)}</h3>
      {day.sessions.map((session) => (
        <div key={session.starts_at} className="space-y-2">
          <p className="text-sm text-slate-800">
            {words.page.session(portalTime(session.starts_at, clinic.timezone, s), portalTime(session.ends_at, clinic.timezone, s))}
            {session.mode === "TOKENS" && ` · ${words.page.placesLeft(session.places_left)}`}
          </p>
          {session.mode === "TOKENS" ? (
            <Link href={requestHref(clinic.slug, doctor.id, session, null, language, viaDirectory)} className={link}>
              {words.page.requestSession}
            </Link>
          ) : (
            <ul className="flex flex-wrap gap-2">
              {session.slots.map((slot) => (
                <li key={slot.starts_at}>
                  <Link
                    href={requestHref(clinic.slug, doctor.id, session, slot.starts_at, language, viaDirectory)}
                    aria-label={words.page.requestSlot(portalTime(slot.starts_at, clinic.timezone, s))}
                    className={link}
                  >
                    {portalTime(slot.starts_at, clinic.timezone, s)}
                  </Link>
                </li>
              ))}
            </ul>
          )}
        </div>
      ))}
    </div>
  );
}
