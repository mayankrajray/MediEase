"use client";

import { ArrowLeft, CalendarCheck, CircleAlert, GraduationCap, IndianRupee, Languages, MapPin, TriangleAlert } from "lucide-react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useId, useRef, useState } from "react";

import { Avatar } from "@/components/ui/Avatar";
import { Button } from "@/components/ui/Button";
import type { GetResponse } from "@/lib/api/client";
import { rupees } from "@/lib/format/money";
import { bookingWords, type BookingWords } from "@/lib/i18n/booking-request";
import { portalDay, portalStrings, portalTime, type PortalLanguage } from "@/lib/i18n/portal";

import { AppointmentPicker } from "./AppointmentPicker";
import { addDays, findOffer, nextAvailableAfter, type Choice } from "./availability";
import { clinicHref, doctorHref, requestHref, type Place } from "./links";
import { PublicHeader } from "./PublicHeader";
import { useAvailability } from "./useAvailability";

type Clinic = GetResponse<"/api/v1/public/clinics/{slug}">;
type Doctor = Clinic["doctors"][number];


/** "Mon 10:00–13:00 · Wed 10:00–13:00" from the doctor's weekly hours. */
export function hoursText(doctor: Doctor, words: BookingWords): string {
  const byDay = new Map<number, string[]>();
  for (const h of doctor.hours) byDay.set(h.weekday, [...(byDay.get(h.weekday) ?? []), `${h.start}–${h.end}`]);
  return [...byDay.entries()]
    .sort(([a], [b]) => a - b)
    .map(([day, spans]) => `${words.page.weekdays[day] ?? ""} ${spans.join(", ")}`)
    .join(" · ");
}

/**
 * A doctor's page (M7d-P3; FR-DIS-03, FR-PUB-02; spec discovery R60; design §7): who they are, in
 * the clinic's published facts only (no photo, rating or counts MediEase does not hold), the date
 * and time picker, and "Request this time".
 *
 * The date and the choice live in the address (`replaceState`, so Back leaves the page rather than
 * stepping through every tap). "Request this time" stays disabled until a time the latest answer
 * offers is chosen; it fetches the times once more before leaving, so a time taken meanwhile is
 * caught here, and a second tap cannot send the patient twice. It is fixed to the bottom of a
 * phone's screen above the safe area, with room kept below the content, and inline from `sm` up.
 */
export function DoctorProfile({
  clinic,
  doctor,
  language,
  viaDirectory,
  today,
  initialDate,
  initialChoice,
}: Readonly<{
  clinic: Clinic;
  doctor: Doctor;
  language: PortalLanguage;
  viaDirectory: boolean;
  today: string;
  initialDate: string;
  initialChoice: Choice | null;
}>) {
  const router = useRouter();
  const all = bookingWords(language);
  const words = all.profile;
  const s = portalStrings(language);
  const ids = { about: useId(), bar: useId() };
  const place: Place = { slug: clinic.slug, language, viaDirectory };
  const availability = useAvailability(clinic.slug, doctor.id, viaDirectory);
  const [date, setDate] = useState(initialDate);
  const [choice, setChoice] = useState<Choice | null>(initialChoice);
  const [leaving, setLeaving] = useState(false);
  const [checkFailed, setCheckFailed] = useState(false);
  const [aboutOpen, setAboutOpen] = useState(false);
  // "Read more" only when three lines actually cut the text (on a wide screen it often fits).
  const aboutRef = useRef<HTMLParagraphElement>(null);
  const [clipped, setClipped] = useState(false);
  useEffect(() => {
    const node = aboutRef.current;
    if (node === null) return;
    const measure = () => setClipped(node.scrollHeight > node.clientHeight + 1);
    measure();
    window.addEventListener("resize", measure);
    return () => window.removeEventListener("resize", measure);
  }, []);

  // Keep the address in step, so Back from the request form and a reload return to this choice.
  useEffect(() => {
    window.history.replaceState(window.history.state, "", doctorHref({ slug: clinic.slug, language, viaDirectory }, doctor.id, date, choice));
  }, [clinic.slug, language, viaDirectory, doctor.id, date, choice]);

  const ready = availability.state.status === "ready";
  const days = availability.state.status === "ready" ? availability.state.days : [];
  const offer = ready ? findOffer(days, date, choice, clinic.timezone) : undefined;
  const firstFree = ready ? nextAvailableAfter(days, addDays(today, -1)) : undefined;
  const noon = (d: string) => `${d}T12:00:00Z`;
  const when = offer === undefined ? undefined : `${portalDay(noon(date), "UTC", s)}, ${portalTime(offer.startsAt, clinic.timezone, s)}`;

  const hours = hoursText(doctor, all);
  const about = [
    words.seesAt(doctor.display_name, [clinic.name, clinic.city].filter((p) => p !== null && p !== "").join(", ")),
    doctor.specialty === null || doctor.specialty === "" ? "" : words.specialty(doctor.specialty),
    doctor.qualification === null || doctor.qualification === "" ? "" : words.qualified(doctor.qualification),
    doctor.languages.length === 0 ? "" : words.speaks(doctor.languages.join(", ")),
    hours === "" ? "" : words.hours(hours),
  ].filter((p) => p !== "");

  function pickDate(next: string) {
    setDate(next);
    setChoice(null);
    setCheckFailed(false);
  }

  function pick(next: Choice | null) {
    setChoice(next);
    setCheckFailed(false);
    // The counts change as others ask: bring them up to date after each choice.
    if (next !== null) void availability.refresh();
  }

  async function request() {
    if (leaving || choice === null || offer === undefined) return;
    setLeaving(true);
    setCheckFailed(false);
    const fresh = await availability.refresh();
    if (fresh === undefined) {
      setCheckFailed(true);
      setLeaving(false);
      return;
    }
    if (findOffer(fresh, date, choice, clinic.timezone) === undefined) {
      setLeaving(false); // the picker now says the time has gone
      return;
    }
    router.push(requestHref(place, doctor.id, choice));
  }

  const subtitle = [doctor.specialty, doctor.qualification].filter((p) => p !== null && p !== "").join(" · ");
  const fact = "min-w-0 space-y-0.5 rounded-lg bg-surface-muted p-3";
  const label = "flex items-center gap-1.5 text-slate-600";

  return (
    <div lang={language} className="min-h-screen bg-canvas">
      <PublicHeader
        language={language}
        switchHref={doctorHref(place, doctor.id, date, choice, language === "hi" ? "en" : "hi")}
        switchTo={all.switchTo}
        switchLabel={all.switchLabel}
      />
      {/* Room for the fixed bar on a phone, so it never covers the last content. */}
      <main className="mx-auto max-w-3xl space-y-5 px-4 pb-44 pt-4 sm:pb-10">
        <Link href={clinicHref(place, date)} className="inline-flex min-h-11 items-center gap-2 text-sm font-semibold text-brand-800 underline-offset-2 hover:underline">
          <ArrowLeft aria-hidden="true" className="size-4" />
          {words.back(clinic.name)}
        </Link>

        <p role="note" className="flex gap-2 rounded-xl border border-warning-line bg-warning-soft p-3 text-sm text-slate-900">
          <TriangleAlert aria-hidden="true" className="mt-0.5 size-4 shrink-0 text-warning" />
          <span>{all.page.emergency}</span>
        </p>

        <section aria-labelledby="doctor-name" className="space-y-4 rounded-card border border-line bg-surface p-4 shadow-card sm:p-5">
          <div className="flex items-start gap-4">
            <Avatar name={doctor.display_name} size="lg" />
            <div className="min-w-0 flex-1 space-y-1">
              <h1 id="doctor-name" className="heading-4 break-words text-slate-900">
                {doctor.display_name}
              </h1>
              {subtitle !== "" && <p className="break-words text-slate-800">{subtitle}</p>}
              <p className="flex gap-1.5 text-sm text-slate-700">
                <MapPin aria-hidden="true" className="mt-0.5 size-4 shrink-0 text-slate-500" />
                <span className="min-w-0 break-words">{[clinic.name, clinic.city].filter((p) => p !== null && p !== "").join(", ")}</span>
              </p>
            </div>
          </div>

          <h2 className="sr-only">{words.facts}</h2>
          <dl className="grid grid-cols-2 gap-2 text-sm">
            {doctor.fee_paise !== null && (
              <div className={fact}>
                <dt className={label}>
                  <IndianRupee aria-hidden="true" className="size-4 shrink-0 text-brand-700" />
                  {words.fee}
                </dt>
                <dd className="font-semibold tabular-nums text-slate-900">{words.feeValue(rupees(doctor.fee_paise))}</dd>
              </div>
            )}
            <div className={fact}>
              <dt className={label}>
                <CalendarCheck aria-hidden="true" className="size-4 shrink-0 text-brand-700" />
                {words.next}
              </dt>
              <dd className="font-semibold text-slate-900">
                {!ready ? <span className="text-slate-500">…</span> : firstFree === undefined ? words.noneSoon : portalDay(noon(firstFree), "UTC", s)}
              </dd>
            </div>
            {doctor.languages.length > 0 && (
              <div className={fact}>
                <dt className={label}>
                  <Languages aria-hidden="true" className="size-4 shrink-0 text-brand-700" />
                  {words.languages}
                </dt>
                <dd className="break-words font-semibold text-slate-900">{doctor.languages.join(", ")}</dd>
              </div>
            )}
            {doctor.qualification !== null && doctor.qualification !== "" && (
              <div className={fact}>
                <dt className={label}>
                  <GraduationCap aria-hidden="true" className="size-4 shrink-0 text-brand-700" />
                  {words.qualification}
                </dt>
                <dd className="break-words font-semibold text-slate-900">{doctor.qualification}</dd>
              </div>
            )}
          </dl>

          <div className="space-y-1">
            <h2 className="heading-6 text-slate-900">{words.about}</h2>
            <p ref={aboutRef} id={ids.about} className={`text-pretty text-slate-700 ${aboutOpen ? "" : "line-clamp-3"}`}>
              {about.join(" ")}
            </p>
            {(clipped || aboutOpen) && (
              <button
                type="button"
                aria-expanded={aboutOpen}
                aria-controls={ids.about}
                onClick={() => setAboutOpen((v) => !v)}
                className="inline-flex min-h-11 cursor-pointer items-center text-sm font-semibold text-brand-800 underline underline-offset-2 hover:text-brand-900"
              >
                {aboutOpen ? words.readLess : words.readMore}
              </button>
            )}
          </div>
        </section>

        <section aria-label={all.page.timesFor(doctor.display_name)} className="rounded-card border border-line bg-surface p-4 shadow-card sm:p-5">
          <AppointmentPicker
            availability={availability.state}
            timezone={clinic.timezone}
            language={language}
            today={today}
            date={date}
            choice={choice}
            onDate={pickDate}
            onChoice={pick}
            onRetry={() => void availability.refresh()}
          />
        </section>

        <div
          id={ids.bar}
          className="fixed inset-x-0 bottom-0 z-30 border-t border-line bg-surface/95 px-4 pb-[max(0.75rem,env(safe-area-inset-bottom))] pt-3 shadow-[0_-4px_12px_rgb(15_23_42/0.08)] backdrop-blur supports-[backdrop-filter]:bg-surface/90 sm:static sm:z-auto sm:rounded-card sm:border sm:bg-surface sm:p-4 sm:shadow-card"
        >
          <div className="mx-auto flex max-w-3xl flex-col gap-2 sm:flex-row sm:items-center sm:gap-4">
            <div className="min-w-0 flex-1 text-sm" aria-live="polite">
              {checkFailed ? (
                <p role="alert" className="flex gap-2 font-medium text-danger">
                  <CircleAlert aria-hidden="true" className="mt-0.5 size-4 shrink-0" />
                  {words.checkFailed}
                </p>
              ) : leaving ? (
                <p className="text-slate-700">{words.checking}</p>
              ) : when === undefined ? (
                <p className="text-slate-700">{words.chooseFirst}</p>
              ) : (
                <p className="text-slate-900">
                  <span className="font-semibold tabular-nums">{when}</span>
                  {doctor.fee_paise !== null && (
                    <span className="text-slate-700">
                      {" · "}
                      {words.feeValue(rupees(doctor.fee_paise))}, {words.payAtClinic.toLowerCase()}
                    </span>
                  )}
                </p>
              )}
            </div>
            <Button type="button" variant="primary" size="lg" loading={leaving} disabled={offer === undefined} onClick={() => void request()} className="w-full sm:w-auto">
              {words.request}
            </Button>
          </div>
        </div>
      </main>
    </div>
  );
}
