import type { Metadata } from "next";
import { cookies } from "next/headers";

import { ForgotPasswordForm } from "@/features/auth/ForgotPasswordForm";
import { forgotWords, PORTAL_LANGUAGE_COOKIE, parsePortalLanguage } from "@/lib/i18n/portal";

export const metadata: Metadata = { title: "Reset your password · MediEase for patients" };

/** In the signed-out pages' language (`me_pt_lang`, M6b-P2 spec R21). */
export default async function PortalForgotPasswordPage() {
  const language = parsePortalLanguage((await cookies()).get(PORTAL_LANGUAGE_COOKIE)?.value);
  return <ForgotPasswordForm kind="patient" signInHref="/portal/sign-in" words={forgotWords(language)} />;
}