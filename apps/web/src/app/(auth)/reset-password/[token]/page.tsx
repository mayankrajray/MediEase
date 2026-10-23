import type { Metadata } from "next";

import { ResetPasswordForm } from "@/features/auth/ResetPasswordForm";

export const metadata: Metadata = { title: "Choose a new password · MediEase", referrer: "no-referrer" };

export default async function ResetPasswordPage({ params }: { params: Promise<{ token: string }> }) {
  const { token } = await params;
  return <ResetPasswordForm kind="staff" token={token} signInPath="/sign-in" forgotPath="/forgot-password" />;
}
