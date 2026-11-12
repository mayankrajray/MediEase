"use client";

import { BellRing } from "lucide-react";

import { DevicePush, type PushApi } from "@/features/pwa/DevicePush";
import { apiGet } from "@/lib/api/client";
import { portalDelete, portalGet, portalPost } from "@/lib/auth/portal-session";
import { deviceWords } from "@/lib/i18n/push";

import { PortalCard, usePortal } from "./PortalShell";

/** M7e-E5: this account's devices for pop-up alerts (spec web-push R50-R54). */
const PORTAL_PUSH: PushApi = {
  config: async () => (await apiGet("/api/v1/push/config")).data,
  list: async () => (await portalGet("/api/v1/portal/push-subscriptions")).data.items,
  add: async (body) => (await portalPost("/api/v1/portal/push-subscriptions", body)).data,
  remove: async (id) => {
    await portalDelete("/api/v1/portal/push-subscriptions/{device_id}", { pathParams: { device_id: id } });
  },
};

/**
 * The Account page's "Pop-up alerts on this device" card. Loaded only when the Account page
 * renders (next/dynamic), so pages that merely link to Account stay within 200 KB (NFR-02).
 */
export function PortalDevicePush({ onSaved }: Readonly<{ onSaved: (text: string) => void }>) {
  const { s, leave } = usePortal();
  const words = deviceWords(s.lang);
  return (
    <PortalCard id="device-push-heading" title={words.title} icon={<BellRing />}>
      <DevicePush owner="patient" words={words} api={PORTAL_PUSH} onSessionError={leave} onSaved={onSaved} />
    </PortalCard>
  );
}
