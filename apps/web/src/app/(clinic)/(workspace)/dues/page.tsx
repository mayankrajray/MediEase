import type { Metadata } from "next";

import { DuesPage } from "@/features/bills/DuesPage";

export const metadata: Metadata = { title: "Dues · MediEase" };

/** Who owes the clinic (M6d-P3, FR-BIL-05). */
export default function Dues() {
  return <DuesPage />;
}
