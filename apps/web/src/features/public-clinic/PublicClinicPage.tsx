"use client";

import { CalendarDays, ChevronRight, CircleAlert, Info, Link2, MapPin, Navigation, Phone, RefreshCw, Share2, TriangleAlert } from "lucide-react";
import Link from "next/link";
import { useEffect, useState, useSyncExternalStore } from "react";

import { Avatar } from "@/components/ui/Avatar";
import { Skeleton } from "@/components/ui/Skeleton";
import { addDays, FEW_PLACES, inWindow, nextAvailableAfter, offersOn, placesOn, type Days } from "@/features/booking/availability";
import { DateStrip, noon } from "@/features/booking/DateStrip";
import { clinicHref, doctorHref, type Place } from "@/features/booking/links";
import { PublicHeader } from "@/features/booking/PublicHeader";
import { useClinicAvailability } from "@/features/booking/useClinicAvailability";
import type { GetResponse } from "@/lib/api/client";
import { rupees } from "@/lib/format/money";
import { bookingWords } from "@/lib/i18n/booking-request";
import { portalDay, portalStrings, portalTime, type PortalLanguage } from "@/lib/i18n/portal";

type Clinic = GetResponse<"/api/v1/public/clinics/{slug}">;

const noSubscribe = () => () => undefined;
const canShareNow = () => typeof navigator.share === "function";
const cannotShareOnServer = () => false;

const BUTTON =
  "inline-flex min-h-11 cursor-pointer items-center justify-center gap-2 rounded-lg border border-slate-300 bg-surface px-3 text-sm font-semibold text-slate-900 transition-colors hover:border-brand-300 hover:bg-brand-50";

/**
 * The public clinic page (M6b-P4; FR-PUB-01, 04, NFR-17, NFR-19; M7d-P4, design §4 decision 3,
 * §7): who the clinic is and how to reach it, then today (or the date in the address) and the
 * doctors who have times free that day, each with "View profile and times". No filters: a small
 * clinic has a handful of doctors. A date when nobody is free offers the next date when someone
 * is. The date lives in the address (`replaceState`), so Back and reload return to it, and the
 * doctor's page opens on the same date. The emergency notice stays above everything else.
 */
export function PublicClinicPage({
  clinic,
  language,
  viaDirectory = false,
  today,
  initialDate,
}: Readonly<{ clinic: Clinic; language: PortalLanguage; viaDirectory?: boolean; today: string; initialDate?: string | undefined }>) {
  const all = bookingWords(language);
  const words = all.page;
  const day = all.clinicDay;
  const s = portalStrings(language);
  const place: Place = { slug: clinic.slug, language, viaDirectory };
  const [date, setDate] = useState(initialDate !== undefined && inWindow(initialDate, today) ? initialDate : today);
  const [copied, setCopied] = useState(false);
  const canShare = useSyncExternalStore(noSubscribe, canShareNow, cannotShareOnServer);
  const { state, refresh } = useClinicAvailability(
    clinic.slug,
    clinic.doctors.map((d) => d.id),
    viaDirectory,
  );

  useEffect(() => {
    window.history.replaceState(window.history.state, "", clinicHref({ slug: clinic.slug, language, viaDirectory }, date));
  }, [clinic.slug, language, viaDirectory, date]);

  const address = [clinic.address_line, clinic.city, clinic.state, clinic.pincode].filter((p) => p !== null && p !== "").join(", ");
  const ready = state.status === "ready";
  const loaded = ready ? clinic.doctors.filter((d) => state.byDoctor[d.id] !== null && state.byDoctor[d.id] !== undefined) : [];
  const daysOf = (id: string): Days => (ready ? (state.byDoctor[id] ?? []) : []);
  const free = loaded.filter((d) => placesOn(daysOf(d.id), date) > 0);
  const someFailed = ready && loaded.length < clinic.doctors.length;
  const leftOn = (d: string) => loaded.reduce((sum, doc) => sum + placesOn(daysOf(doc.id), d), 0);
  const nextDates = loaded.map((d) => nextAvailableAfter(daysOf(d.id), date)).filter((d): d is string => d !== undefined);
  const firstDates = loaded.map((d) => nextAvailableAfter(daysOf(d.id), addDays(today, -1))).filter((d): d is string => d !== undefined);
  const next = nextDates.sort()[0];
  const first = firstDates.sort()[0];
  const target = next ?? (first !== date ? first : undefined);

  async function copy() {
    try {
      await navigator.clipboard.writeText(`${window.location.origin}/c/${clinic.slug}`);
      setCopied(true);
    } catch {
      setCopied(false);
    }
  }

  async function share() {
    try {
      await navigator.share({ title: clinic.name, url: `${window.location.origin}/c/${clinic.slug}` });
    } catch {
      // Dismissed by the person: nothing to do.
    }
  }

  return (
    <div lang={language} className="min-h-screen bg-canvas">
      <PublicHeader language={language} switchHref={clinicHref(place, date, language === "hi" ? "en" : "hi")} switchTo={all.switchTo} switchLabel={all.switchLabel} />
      <main className="mx-auto max-w-3xl space-y-5 px-4 pb-10 pt-5">
        <p role="note" className="flex gap-2 rounded-xl border border-warning-line bg-warning-soft p-3 text-sm text-slate-900">
          <TriangleAlert aria-hidden="true" className="mt-0.5 size-4 shrink-0 text-warning" />
          <span>{words.emergency}</span>
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
            <ul aria-label={words.specialties} className="flex flex-wrap gap-2 text-sm text-slate-800">
              {clinic.specialties.map((sp) => (
                <li key={sp} className="rounded-md bg-surface-muted px-2 py-1">
                  {sp}
                </li>
              ))}
            </ul>
          )}
          <div className="grid grid-cols-2 gap-2 sm:flex sm:flex-wrap">
            {clinic.phone_e164 !== null && (
              <a href={`tel:${clinic.phone_e164}`} className={BUTTON}>
                <Phone aria-hidden="true" className="size-4" />
                {words.call}
              </a>
            )}
            {clinic.map_url !== null && (
              <a href={clinic.map_url} target="_blank" rel="noopener noreferrer" className={BUTTON}>
                <Navigation aria-hidden="true" className="size-4" />
                {words.directions}
              </a>
            )}
            {canShare && (
              <button type="button" onClick={() => void share()} className={BUTTON}>
                <Share2 aria-hidden="true" className="size-4" />
                {words.share}
              </button>
            )}
            <button type="button" onClick={() => void copy()} className={BUTTON}>
              <Link2 aria-hidden="true" className="size-4" />
              {words.copy}
            </button>
          </div>
          <p role="status" aria-live="polite" className={copied ? "text-sm font-medium text-success" : "sr-only"}>
            {copied ? words.copied : ""}
          </p>
          <p className="flex gap-2 rounded-lg bg-surface-muted p-3 text-sm text-slate-700">
            <Info aria-hidden="true" className="mt-0.5 size-4 shrink-0 text-info" />
            <span>{words.howItWorks}</span>
          </p>
        </section>

        <div className="space-y-5 rounded-card border border-line bg-surface p-4 shadow-card sm:p-5">
          <DateStrip language={language} today={today} date={date} onDate={setDate} left={ready ? leftOn : undefined} />

          <section aria-labelledby="doctors-heading" aria-busy={state.status === "loading"} className="space-y-3">
            <h2 id="doctors-heading" className="heading-6 text-slate-900">
              {day.heading(portalDay(noon(date), "UTC", s))}
            </h2>

            {state.status === "loading" && (
              <div>
                <p role="status" className="sr-only">
                  {day.loading}
                </p>
                <div aria-hidden="true" className="space-y-3">
                  <Skeleton className="h-28" />
                  <Skeleton className="h-28" />
                </div>
              </div>
            )}

            {(state.status === "failed" || someFailed) && (
              <div role="alert" className="space-y-3 rounded-xl border border-danger-line bg-danger-soft p-4 text-slate-900">
                <p className="flex gap-2 font-semibold">
                  <CircleAlert aria-hidden="true" className="mt-0.5 size-4 shrink-0 text-danger" />
                  {state.status === "failed" ? day.failed : day.someFailed}
                </p>
                <button type="button" onClick={refresh} className={BUTTON}>
                  <RefreshCw aria-hidden="true" className="size-4" />
                  {words.retry}
                </button>
              </div>
            )}

            {ready && free.length === 0 && !(someFailed && loaded.length === 0) && (
              <div className="space-y-3 rounded-card border border-dashed border-slate-300 px-4 py-6 text-center">
                <p className="text-slate-800">{target === undefined ? all.picker.noneInWindow : day.none}</p>
                {target !== undefined && (
                  <button
                    type="button"
                    onClick={() => setDate(target)}
                    className="inline-flex min-h-11 cursor-pointer items-center justify-center gap-2 rounded-lg bg-brand-700 px-4 font-semibold text-white transition-colors hover:bg-brand-800"
                  >
                    <CalendarDays aria-hidden="true" className="size-4" />
                    {next === undefined ? all.picker.firstAvailable(portalDay(noon(target), "UTC", s)) : all.picker.nextAvailable(portalDay(noon(target), "UTC", s))}
                  </button>
                )}
              </div>
            )}

            {free.length > 0 && (
              <ul className="space-y-3">
                {free.map((d) => {
                  const left = placesOn(daysOf(d.id), date);
                  const earliest = offersOn(daysOf(d.id), date, clinic.timezone)[0];
                  const about = [d.specialty, d.qualification].filter((p) => p !== null && p !== "").join(" · ");
                  return (
                    <li key={d.id} className="space-y-3 rounded-card border border-line p-4">
                      <div className="flex items-start gap-3">
                        <Avatar name={d.display_name} />
                        <div className="min-w-0 flex-1 space-y-0.5">
                          <p className="break-words font-semibold text-slate-900">{d.display_name}</p>
                          {about !== "" && <p className="break-words text-sm text-slate-800">{about}</p>}
                        </div>
                      </div>
                      <ul className="flex flex-wrap gap-2 text-sm">
                        {d.fee_paise !== null && <li className="rounded-md bg-surface-muted px-2 py-1 text-slate-800">{words.fee(rupees(d.fee_paise))}</li>}
                        {earliest !== undefined && <li className="rounded-md bg-surface-muted px-2 py-1 tabular-nums text-slate-800">{day.from(portalTime(earliest.startsAt, clinic.timezone, s))}</li>}
                        <li
                          className={`rounded-md px-2 py-1 font-semibold tabular-nums text-slate-900 ring-1 ${left <= FEW_PLACES ? "bg-warning-soft ring-warning-line" : "bg-success-soft ring-success-line"}`}
                        >
                          {all.picker.placesOn(left)}
                        </li>
                      </ul>
                      <Link
                        href={doctorHref(place, d.id, date)}
                        className="inline-flex min-h-11 items-center justify-center gap-2 rounded-lg border border-brand-300 bg-brand-50 px-4 font-semibold text-brand-900 transition-colors hover:border-brand-700 hover:bg-brand-100 max-sm:w-full"
                      >
                        {day.view}
                        <span className="sr-only">: {d.display_name}</span>
                        <ChevronRight aria-hidden="true" className="size-4" />
                      </Link>
                    </li>
                  );
                })}
              </ul>
            )}

            {ready && free.length > 0 && loaded.length > free.length && <p className="text-sm text-slate-700">{day.others(loaded.length - free.length)}</p>}
          </section>
        </div>
      </main>
    </div>
  );
}
