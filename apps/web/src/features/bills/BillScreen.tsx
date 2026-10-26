"use client";

import { BillDetail } from "./BillDetail";

/** The bill page: the bill itself, and (from P3, P4) its payments and receipts. */
export function BillScreen({ billId }: Readonly<{ billId: string }>) {
  return <BillDetail billId={billId} />;
}
