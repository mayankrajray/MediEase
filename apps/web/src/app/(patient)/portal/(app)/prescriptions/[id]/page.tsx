import type { Metadata } from "next";

import { PortalPrescription } from "@/features/portal/PortalPrescriptions";

export const metadata: Metadata = { title: "Prescription · MediEase for patients", referrer: "no-referrer" };

type Search = Promise<Record<string, string | string[] | undefined>>;

/** One prescription (M6b-P2; spec R19): `?lang=en|hi`, else the account's language. */
export default async function PortalPrescriptionPage({
  params,
  searchParams,
}: Readonly<{ params: Promise<{ id: string }>; searchParams: Search }>) {
  const { id } = await params;
  const { lang } = await searchParams;
  return <PortalPrescription rxId={id} {...(lang === "en" || lang === "hi" ? { lang } : {})} />;
}