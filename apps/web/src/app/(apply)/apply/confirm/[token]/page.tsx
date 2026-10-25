import type { Metadata } from "next";

import { ConfirmApplication } from "@/features/apply/ConfirmApplication";

export const metadata: Metadata = {
  title: "Confirm your application · MediEase",
  robots: { index: false, follow: false },
  referrer: "no-referrer",
};

/** The confirmation link of an application (M6c-P1; spec clinic-onboarding R11, R12). */
export default async function ConfirmApplicationPage({ params }: Readonly<{ params: Promise<{ token: string }> }>) {
  const { token } = await params;
  return <ConfirmApplication token={token} />;
}
