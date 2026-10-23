import type { Metadata } from "next";

import { ForgotPasswordForm } from "@/features/auth/ForgotPasswordForm";

export const metadata: Metadata = { title: "Reset your password · MediEase" };

export default function ForgotPasswordPage() {
  return <ForgotPasswordForm kind="staff" signInHref="/sign-in" />;
}
