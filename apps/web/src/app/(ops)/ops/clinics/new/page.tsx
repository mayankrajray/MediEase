import type { Metadata } from "next";

import { CreateClinicWizard } from "@/features/ops/CreateClinicWizard";

export const metadata: Metadata = { title: "Create clinic · Ops · MediEase" };

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

/** `?clinic=<id>` resumes a clinic that is still being set up; anything that is not an ID is ignored. */
export default async function NewClinicPage({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const { clinic } = await searchParams;
  const raw = Array.isArray(clinic) ? clinic[0] : clinic;
  const resumeClinicId = raw !== undefined && UUID.test(raw) ? raw : undefined;
  return <CreateClinicWizard {...(resumeClinicId === undefined ? {} : { resumeClinicId })} />;
}
