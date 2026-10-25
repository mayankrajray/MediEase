import type { Metadata } from "next";

import { BookingRequests } from "@/features/appointments/BookingRequests";

export const metadata: Metadata = { title: "Booking requests · MediEase" };

/** M6b-P4 (spec R22): reached from the nav and from a "New request" notification. */
export default function BookingRequestsPage() {
  return <BookingRequests />;
}
