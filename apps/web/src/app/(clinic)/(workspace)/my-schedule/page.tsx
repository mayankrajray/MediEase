import type { Metadata } from "next";

import { MySchedule } from "@/features/schedule/MySchedule";

export const metadata: Metadata = { title: "My schedule · MediEase" };

export default function MySchedulePage() {
  return <MySchedule />;
}
