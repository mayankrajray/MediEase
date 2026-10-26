import type { Metadata } from "next";
import { Suspense } from "react";

import { PortalAssistant } from "@/features/assistant/PortalAssistant";

export const metadata: Metadata = { title: "Assistant · MediEase for patients" };

/** M7a-P4 (spec assistant §6): the patient assistant. */
export default function PortalAssistantPage() {
  return (
    <Suspense>
      <PortalAssistant />
    </Suspense>
  );
}
