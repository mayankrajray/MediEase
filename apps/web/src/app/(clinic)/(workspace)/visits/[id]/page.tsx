import type { Metadata } from "next";

import { ConsultationScreen } from "@/features/visits/ConsultationScreen";

// The title never names the patient (apps/web/CLAUDE.md).
export const metadata: Metadata = { title: "Consultation · MediEase" };

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

/** One visit's consultation (M4-P6). A path that is not an ID reads like any unknown visit. */
export default async function VisitPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return <ConsultationScreen key={id} visitId={UUID.test(id) ? id : "00000000-0000-0000-0000-000000000000"} />;
}
