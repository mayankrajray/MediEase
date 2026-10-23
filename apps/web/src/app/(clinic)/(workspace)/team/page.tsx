import type { Metadata } from "next";

import { TeamPage } from "@/features/team/TeamPage";

export const metadata: Metadata = { title: "Team · MediEase" };

export default function TeamRoute() {
  return <TeamPage />;
}
