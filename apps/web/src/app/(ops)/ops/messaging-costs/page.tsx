import type { Metadata } from "next";

import { MessagingCosts } from "@/features/ops/MessagingCosts";

export const metadata: Metadata = { title: "Messaging costs · Ops · MediEase" };

export default function OpsMessagingCostsPage() {
  return <MessagingCosts />;
}
