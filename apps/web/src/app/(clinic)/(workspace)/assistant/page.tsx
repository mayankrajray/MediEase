import type { Metadata } from "next";

import { StaffAssistant } from "@/features/assistant/StaffAssistant";

export const metadata: Metadata = { title: "Assistant · MediEase" };

/** M7a-P5 (spec assistant §6): the staff assistant, for every role. */
export default function AssistantPage() {
  return <StaffAssistant />;
}
