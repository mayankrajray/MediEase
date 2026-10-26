import type { Metadata } from "next";
import { cookies } from "next/headers";
import { notFound } from "next/navigation";

import { PublicClinicPage } from "@/features/public-clinic/PublicClinicPage";
import { ApiError, apiGet, type GetResponse } from "@/lib/api/client";
import { pickLanguage } from "@/lib/i18n/booking-request";
import { PORTAL_LANGUAGE_COOKIE } from "@/lib/i18n/portal";

type Search = Record<string, string | string[] | undefined>;
type Clinic = GetResponse<"/api/v1/public/clinics/{slug}">;
type Params = Promise<{ slug: string; doctor: string }>;

const NOINDEX = { index: false, follow: false } as const;
const INDEX = { index: true, follow: true } as const;

/** The clinic with the doctor shown on it, or the same 404 as an unknown page (spec R59, NFR-19). */
async function load(slug: string, doctorId: string): Promise<{ clinic: Clinic; doctor: Clinic["doctors"][number] }> {
  try {
    const clinic = (await apiGet("/api/v1/public/clinics/{slug}", { pathParams: { slug } })).data;
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

/**
 * A doctor's public profile (M6c-P5; FR-DIS-03, spec R60): the clinic page for that doctor alone,
 * with their qualification, specialty, languages, fee, hours and free times. A doctor who is not
 * shown, or a clinic without a public page, is the same 404.
 */
export default async function DoctorProfileRoute({ params, searchParams }: Readonly<{ params: Params; searchParams: Promise<Search> }>) {
  const { slug, doctor: doctorId } = await params;
  const query = await searchParams;
  const { clinic, doctor } = await load(slug, doctorId);
  const language = pickLanguage(query.lang, (await cookies()).get(PORTAL_LANGUAGE_COOKIE)?.value);
  return <PublicClinicPage clinic={clinic} language={language} profileOf={doctor.id} />;
}
