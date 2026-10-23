import type { Metadata } from "next";

import { ResetPasswordForm } from "@/features/auth/ResetPasswordForm";

export const metadata: Metadata = {
  title: "Choose a new password · MediEase for patients",
  referrer: "no-referrer",
};

export default async function PortalResetPasswordPage({ params }: { params: Promise<{ token: string }> }) {
  const { token } = await params;
  return (
    <ResetPasswordForm
      kind="patient"
      token={token}
      signInPath="/portal/sign-in"
      forgotPath="/portal/forgot-password"
    />
  );
}
