import type { Metadata } from "next";

import { AcceptInvite } from "@/features/portal/LinkRecords";

export const metadata: Metadata = {
  title: "Link your records · MediEase for patients",
  referrer: "no-referrer",
};

/** M6b-P1: a clinic's invite to the patient app (the proxy sends a signed-out visitor to sign in). */
export default async function PortalInvitePage({
  params,
}: {
  params: Promise<{ token: string }>;
}) {
  const { token } = await params;
  return <AcceptInvite token={token} />;
}
