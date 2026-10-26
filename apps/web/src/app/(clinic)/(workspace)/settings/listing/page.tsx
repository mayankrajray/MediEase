import type { Metadata } from "next";

import { DirectoryListing } from "@/features/listing/DirectoryListing";

export const metadata: Metadata = { title: "Directory · MediEase" };

/** The owner's directory listing and doctor visibility (M6c-P4, FR-ONB-09, 10). */
export default function DirectoryListingPage() {
  return <DirectoryListing />;
}
