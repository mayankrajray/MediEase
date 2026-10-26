import type { Metadata } from "next";

import { BillsList } from "@/features/bills/BillsList";

export const metadata: Metadata = { title: "Bills · MediEase" };

/** The clinic's bills (M6d-P2, FR-BIL-02). */
export default function BillsPage() {
  return <BillsList />;
}
