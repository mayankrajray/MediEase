import type { Metadata } from "next";

import { VerifyEmail } from "@/features/portal/VerifyEmail";

export const metadata: Metadata = { title: "Confirm your email · MediEase for patients", referrer: "no-referrer" };

export default async function VerifyEmailPage({ params }: { params: Promise<{ token: string }> }) {
  const { token } = await params;
  return <VerifyEmail token={token} />;
}
