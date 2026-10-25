import type { Metadata } from "next";

import { ReviewApplication } from "@/features/ops/reviewer/ReviewApplication";

export const metadata: Metadata = { title: "Application · Ops · MediEase" };

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

/** M6c-P2, P3: one application, its checks, reject and approve (OPS_REVIEWER). A path that is
 * not an ID reads like any unknown application. */
export default async function OpsApplicationPage({ params }: Readonly<{ params: Promise<{ id: string }> }>) {
  const { id } = await params;
  return <ReviewApplication key={id} applicationId={UUID.test(id) ? id : "00000000-0000-0000-0000-000000000000"} />;
}
