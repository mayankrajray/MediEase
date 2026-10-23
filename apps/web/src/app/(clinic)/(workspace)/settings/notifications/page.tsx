import type { Metadata } from "next";

import { NotificationPreferences } from "@/features/notifications/NotificationPreferences";

export const metadata: Metadata = { title: "Notifications · MediEase" };

/** Every member's own notification settings (M6a-P7, FR-NTF-05). */
export default function NotificationSettingsPage() {
  return <NotificationPreferences />;
}
