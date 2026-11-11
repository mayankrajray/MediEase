import type { Metadata } from "next";
import { cookies } from "next/headers";
import { notFound } from "next/navigation";

import { clinicToday, inWindow, type Choice } from "@/features/booking/availability";
import { DoctorProfile } from "@/features/booking/DoctorProfile";
import { ApiError, apiGet, type GetResponse } from "@/lib/api/client";
import { pickLanguage } from "@/lib/i18n/booking-request";
import { PORTAL_LANGUAGE_COOKIE } from "@/lib/i18n/portal";

type Search = Record<string, string | string[] | undefined>;
type Clinic = GetResponse<"/api/v1/public/clinics/{slug}">;
type Params = Promise<{ slug: string; doctor: string }>;

const NOINDEX = { index: false, follow: false } as const;
const INDEX = { index: true, follow: true } as const;

/** The clinic with the doctor shown on it, or the same 404 as an unknown page (spec R59, NFR-19). */
async function load(slug: string, doctorId: string, via = false): Promise<{ clinic: Clinic; doctor: Clinic["doctors"][number] }> {
  try {
    // M6c-P7 (discovery R11): opened from search, the API applies the directory's rule too.
    const clinic = (await apiGet("/api/v1/public/clinics/{slug}", { pathParams: { slug }, ...(via ? { query: { via: "directory" } } : {}) })).data;
    const doctor = clinic.doctors.find((d) => d.id === doctorId);
    if (doctor === undefined) notFound();
    return { clinic, doctor };
  } catch (error) {
    if (error instanceof ApiError && (error.code === "REQ_NOT_FOUND" || error.status === 404)) notFound();
    throw error;
  }
}

export async function generateMetadata({ params }: Readonly<{ params: Params }>): Promise<Metadata> {
  const { slug, doctor: doctorId } = await params;
  try {
    const { clinic, doctor } = await load(slug, doctorId);
    const place = [clinic.city, clinic.state].filter((part) => part !== null && part !== "").join(", ");
    const about = [doctor.qualification, doctor.specialty].filter((p) => p !== null && p !== "").join(", ");
    return {
      title: `${doctor.display_name} · ${clinic.name} · MediEase`,
      description: [about, clinic.name, place].filter((p) => p !== "").join(" · "),
      robots: clinic.indexable ? INDEX : NOINDEX,
      alternates: { canonical: `/c/${clinic.slug}/doctors/${doctor.id}` },
    };
  } catch {
    return { title: "Doctor · MediEase", robots: NOINDEX };
  }
}

function one(value: string | string[] | undefined): string {
  return (Array.isArray(value) ? value[0] : value) ?? "";
}

/** M7d-P3: the date and time from the address, if they still make sense; else today, nothing chosen. */
function chosen(query: Search, today: string): { date: string; choice: Choice | null } {
  const date = one(query.date);
  if (!inWindow(date, today)) return { date: today, choice: null };
  const session = one(query.session);
  const slot = one(query.slot);
  const valid = (iso: string) => iso !== "" && !Number.isNaN(Date.parse(iso));
  return { date, choice: valid(session) ? { session, slot: valid(slot) ? slot : null } : null };
}

/**
 * A doctor's public profile (M6c-P5; FR-DIS-03, spec R60; M7d-P3): who they are, the date and time
 * picker, and "Request this time". A doctor who is not shown, or a clinic without a public page, is
 * the same 404. Today is the clinic's date, worked out here so the page and the browser agree.
 */
export default async function DoctorProfileRoute({ params, searchParams }: Readonly<{ params: Params; searchParams: Promise<Search> }>) {
  const { slug, doctor: doctorId } = await params;
  const query = await searchParams;
  const via = query.via === "directory";
  const { clinic, doctor } = await load(slug, doctorId, via);
  const language = pickLanguage(query.lang, (await cookies()).get(PORTAL_LANGUAGE_COOKIE)?.value);
  const today = clinicToday(new Date(), clinic.timezone);
  const { date, choice } = chosen(query, today);
  return <DoctorProfile clinic={clinic} doctor={doctor} language={language} viaDirectory={via} today={today} initialDate={date} initialChoice={choice} />;
}
