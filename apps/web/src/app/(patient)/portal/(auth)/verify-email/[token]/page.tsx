import type { Metadata } from "next";
import { cookies } from "next/headers";

import { VerifyEmail } from "@/features/portal/VerifyEmail";
import { PORTAL_LANGUAGE_COOKIE, parsePortalLanguage } from "@/lib/i18n/portal";

export const metadata: Metadata = { title: "Confirm your email · MediEase for patients", referrer: "no-referrer" };

export default async function VerifyEmailPage({ params }: { params: Promise<{ token: string }> }) {
  const { token } = await params;
  const language = parsePortalLanguage((await cookies()).get(PORTAL_LANGUAGE_COOKIE)?.value);
  return <VerifyEmail token={token} language={language} />;
}
