import type { Metadata } from "next";

import { TodayDashboard } from "@/features/dashboard/TodayDashboard";

export const metadata: Metadata = { title: "Today · MediEase" };

export default function TodayPage() {
  return <TodayDashboard />;
}
