import type { Metadata } from "next";

import { ForgotPasswordForm } from "@/features/auth/ForgotPasswordForm";

export const metadata: Metadata = { title: "Reset your password · MediEase for patients" };

export default function PortalForgotPasswordPage() {
  return <ForgotPasswordForm kind="patient" signInHref="/portal/sign-in" />;
}
