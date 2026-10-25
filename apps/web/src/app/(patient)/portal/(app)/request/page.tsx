import type { Metadata } from "next";
import { Suspense } from "react";

import { RequestBooking } from "@/features/portal/RequestBooking";

export const metadata: Metadata = { title: "Ask for a time · MediEase for patients", robots: { index: false, follow: false } };

/** The booking-request form behind a clinic's public page (M6b-P4, spec R9-R12). */
export default function PortalRequestPage() {
  return (
    <Suspense fallback={null}>
      <RequestBooking />
    </Suspense>
  );
}
