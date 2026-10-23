import type { Metadata } from "next";

import { TeamPage } from "@/features/team/TeamPage";

export const metadata: Metadata = { title: "Team · MediEase" };

/** `?invite=1` (the owner's *Invite someone* on Today, M6a-P6) opens the invite drawer. */
export default async function TeamRoute({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const { invite } = await searchParams;
  return <TeamPage initialInvite={invite !== undefined} />;
}
