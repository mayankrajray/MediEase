import type { Metadata } from "next";

import { QUEUE_PATH } from "@/features/auth/landing";
import { ClinicChooser } from "@/features/shell/ClinicChooser";
import { safeNextPath } from "@/lib/auth/safe-next";

export const metadata: Metadata = { title: "Choose a clinic · MediEase" };

export default async function SelectClinicPage({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const { next } = await searchParams;
  const raw = Array.isArray(next) ? next[0] : next;
  return <ClinicChooser next={safeNextPath(raw, QUEUE_PATH)} />;
}
