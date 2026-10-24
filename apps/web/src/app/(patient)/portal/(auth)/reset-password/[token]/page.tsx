import type { Metadata } from "next";
import { cookies } from "next/headers";

import { ResetPasswordForm } from "@/features/auth/ResetPasswordForm";
import { PORTAL_LANGUAGE_COOKIE, parsePortalLanguage, resetWords } from "@/lib/i18n/portal";

export const metadata: Metadata = {
  title: "Choose a new password · MediEase for patients",
  referrer: "no-referrer",
};

/** In the signed-out pages' language (`me_pt_lang`, M6b-P2 spec R21). */
export default async function PortalResetPasswordPage({ params }: { params: Promise<{ token: string }> }) {
  const { token } = await params;
  const language = parsePortalLanguage((await cookies()).get(PORTAL_LANGUAGE_COOKIE)?.value);
  return (
    <ResetPasswordForm
      kind="patient"
      token={token}
      signInPath="/portal/sign-in"
      forgotPath="/portal/forgot-password"
      words={resetWords(language)}
    />
  );
}