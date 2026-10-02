import type { Metadata } from "next";

import { StatusView } from "@/features/platform/StatusView";
import { getPlatformStatus } from "@/features/platform/status";

export const metadata: Metadata = { title: "Status · MediEase" };

/**
 * Rendered on the server for every request: the API is called over the
 * internal network (API_INTERNAL_URL) and the page needs no client JavaScript.
 */
export default async function StatusPage() {
  return (
    <main>
      <StatusView status={await getPlatformStatus()} />
    </main>
  );
}
