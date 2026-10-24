import type { Metadata } from "next";

import { BookingsToMove } from "@/features/appointments/BookingsToMove";

export const metadata: Metadata = { title: "Bookings to move · MediEase" };

/** M6a-P8 (FR-APT-09): reached from Today's tile, the queue's banner and a notification. */
export default function BookingsToMovePage() {
  return <BookingsToMove />;
}
