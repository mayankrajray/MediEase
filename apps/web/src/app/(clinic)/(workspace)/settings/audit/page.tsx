import type { Metadata } from "next";

import { AuditLog } from "@/features/audit/AuditLog";

export const metadata: Metadata = { title: "Audit log · MediEase" };

/** The clinic's audit log, for its owners (M6a-P8, FR-AUD-03). */
export default function AuditLogPage() {
  return <AuditLog />;
}
