"use client";

import { BillDetail } from "./BillDetail";
import { PaymentsPanel } from "./PaymentsPanel";

/** The bill page: the bill itself, its payments (P3) and, from P4, its receipts. */
export function BillScreen({ billId }: Readonly<{ billId: string }>) {
  return <BillDetail billId={billId} extra={(bill, show) => (bill.status === "DRAFT" ? null : <PaymentsPanel bill={bill} onChange={show} />)} />;
}
