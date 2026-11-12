import type { Metadata } from "next";
import { cookies } from "next/headers";
import { notFound } from "next/navigation";

import { clinicToday } from "@/features/booking/availability";
import { PublicClinicPage } from "@/features/public-clinic/PublicClinicPage";
import { ApiError, apiGet, type GetResponse } from "@/lib/api/client";
import { forwardedClient } from "@/lib/api/forwarded";
import { pickLanguage } from "@/lib/i18n/booking-request";
import { PORTAL_LANGUAGE_COOKIE } from "@/lib/i18n/portal";

type Search = Record<string, string | string[] | undefined>;
type Clinic = GetResponse<"/api/v1/public/clinics/{slug}">;

// FR-DIS-06 (M6c-P5, R62): indexed only when the API says so (discoverable and not opted out);
// the head carries the name and place only.
const NOINDEX = { index: false, follow: false } as const;
const INDEX = { index: true, follow: true } as const;

/** M6c-P7 (discovery R11): opened from search, the API applies the directory's rule too. */
function viaDirectory(search: Search): boolean {
  return search.via === "directory";
}

async function load(slug: string, via: boolean): Promise<Clinic> {
  try {
    return (await apiGet("/api/v1/public/clinics/{slug}", { headers: await forwardedClient(), pathParams: { slug }, ...(via ? { query: { via: "directory" } } : {}) })).data;
  } catch (error) {
    // An unknown slug and a clinic without a public page are the same answer (spec R2).
    if (error instanceof ApiError && (error.code === "REQ_NOT_FOUND" || error.status === 404)) notFound();
    throw error;
  }
}

export async function generateMetadata({ params }: Readonly<{ params: Promise<{ slug: string }> }>): Promise<Metadata> {
  const { slug } = await params;
  try {
    const clinic = (await apiGet("/api/v1/public/clinics/{slug}", { headers: await forwardedClient(), pathParams: { slug } })).data;
    const place = [clinic.city, clinic.state].filter((part) => part !== null && part !== "").join(", ");
    const title = `${clinic.name} · MediEase`;
    // Name and address only: no doctor, no hours, nothing a share preview should not carry.
    return {
      title,
      description: place === "" ? clinic.name : `${clinic.name}, ${place}`,
      robots: clinic.indexable ? INDEX : NOINDEX,
      alternates: { canonical: `/c/${clinic.slug}` },
      openGraph: { title: clinic.name, ...(place === "" ? {} : { description: place }), type: "website" },
    };
  } catch {
    return { title: "Clinic · MediEase", robots: NOINDEX };
  }
}

/**
 * A clinic's public page (M6b-P4; FR-PUB-01, 04, NFR-17, NFR-19; M7d-P4): who they are, and the
 * doctors free on today or the date in the address. Rendered on the server, English or Hindi,
 * 360 px first. Nothing here is signed in: a doctor's page leads to the portal's request form,
 * which asks the patient to sign in and brings them back to the same time. Today is the clinic's
 * date, worked out here so the page and the browser agree.
 */
export default async function PublicClinicRoute({ params, searchParams }: Readonly<{ params: Promise<{ slug: string }>; searchParams: Promise<Search> }>) {
  const { slug } = await params;
  const query = await searchParams;
  const via = viaDirectory(query);
  const clinic = await load(slug, via);
  const language = pickLanguage(query.lang, (await cookies()).get(PORTAL_LANGUAGE_COOKIE)?.value);
  const date = Array.isArray(query.date) ? query.date[0] : query.date;
  return <PublicClinicPage clinic={clinic} language={language} viaDirectory={via} today={clinicToday(new Date(), clinic.timezone)} initialDate={date} />;
}
