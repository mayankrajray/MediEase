import type { Metadata } from "next";

import { ScheduleSettings } from "@/features/schedule/ScheduleSettings";

export const metadata: Metadata = { title: "Schedule · MediEase" };

export default function SchedulePage() {
  return <ScheduleSettings />;
}