import type { Metadata } from "next";

import { CollectionPage } from "@/features/bills/CollectionPage";

export const metadata: Metadata = { title: "Collection · MediEase" };

/** The day's collection (M6d-P5, FR-BIL-06). */
export default function Collection() {
  return <CollectionPage />;
}
