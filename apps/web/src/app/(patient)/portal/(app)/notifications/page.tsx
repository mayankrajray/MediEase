import type { Metadata } from "next";

import { PortalNotifications } from "@/features/portal/PortalNotifications";

export const metadata: Metadata = { title: "Notifications · MediEase for patients" };

/** *Notifications* (M6b-P6; spec R55, R67, R68). */
export default function PortalNotificationsPage() {
  return <PortalNotifications />;
}
