import type { Metadata } from "next";

import { PendingFollowUps } from "@/features/reminders/PendingFollowUps";

export const metadata: Metadata = { title: "Follow-ups · MediEase" };

export default function FollowUpsPage() {
  return <PendingFollowUps />;
}
