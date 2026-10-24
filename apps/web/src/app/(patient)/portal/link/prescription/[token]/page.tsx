import type { Metadata } from "next";

import { LinkFromPrescription } from "@/features/portal/LinkRecords";

export const metadata: Metadata = {
  title: "Save your records · MediEase for patients",
  referrer: "no-referrer",
};

/** M6b-P1: *Save to my MediEase* from a prescription page (the last-4 check, verified accounts). */
export default async function PortalPrescriptionLinkPage({
  params,
}: {
  params: Promise<{ token: string }>;
}) {
  const { token } = await params;
  return <LinkFromPrescription token={token} />;
}
