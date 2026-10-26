import type { Metadata } from "next";

import { BillScreen } from "@/features/bills/BillScreen";

// The title never names the patient (apps/web/CLAUDE.md).
export const metadata: Metadata = { title: "Bill · MediEase" };

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

/** One bill (M6d-P2). A path that is not an ID reads like any unknown bill. */
export default async function BillPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  return <BillScreen key={id} billId={UUID.test(id) ? id : "00000000-0000-0000-0000-000000000000"} />;
}
