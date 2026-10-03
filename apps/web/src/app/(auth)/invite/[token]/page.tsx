import type { Metadata } from "next";

import { AcceptInviteForm } from "@/features/auth/AcceptInviteForm";

export const metadata: Metadata = { title: "Join your clinic · MediEase" };

export default async function InvitePage({ params }: { params: Promise<{ token: string }> }) {
  const { token } = await params;
  return <AcceptInviteForm token={token} />;
}
