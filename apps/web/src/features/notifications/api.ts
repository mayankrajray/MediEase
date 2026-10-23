"use client";

/**
 * The notification centre and preferences (M6a-P7; FR-NTF-03, FR-NTF-05). Every call names the
 * active clinic when the person has several and refreshes an expired session once. Each acts on
 * the signed-in member's own notifications only; the API answers 404 for anybody else's.
 */

import { useMemo } from "react";

import { useSession } from "@/features/auth/SessionProvider";
import { apiGetConditional, type ConditionalResult, type RequestOptions } from "@/lib/api/client";
import type { components } from "@/lib/api/schema";
import { sessionGet, sessionPost, sessionPut, withSessionRefresh } from "@/lib/auth/refresh";

export type Notification = components["schemas"]["Notification"];
export type NotificationSummary = components["schemas"]["NotificationSummary"];
export type NotificationKind = components["schemas"]["NotificationKind"];
export type Preference = components["schemas"]["NotificationPreferences"]["items"][number];

export interface NotificationsApi {
  readonly clinicId: string | undefined;
  /** The latest 30, newest first. */
  readonly list: () => Promise<readonly Notification[]>;
  readonly summary: (etag: string | undefined, signal: AbortSignal) => Promise<ConditionalResult<NotificationSummary>>;
  readonly read: (id: string) => Promise<Notification>;
  readonly readAll: () => Promise<number>;
  readonly preferences: () => Promise<readonly Preference[]>;
  readonly setPreference: (kind: NotificationKind, enabled: boolean) => Promise<readonly Preference[]>;
}

export function useNotificationsApi(): NotificationsApi {
  const { clinic } = useSession();
  const clinicId = clinic.kind === "active" && clinic.sendClinicHeader ? clinic.membership.clinic_id : undefined;

  return useMemo(() => {
    const base: RequestOptions = clinicId === undefined ? {} : { clinicId };
    return {
      clinicId,
      list: async () => (await sessionGet("/api/v1/notifications", base)).data.items,
      summary: (etag, signal) =>
        withSessionRefresh(() => apiGetConditional("/api/v1/notifications/summary", etag, { ...base, signal })),
      read: async (id) =>
        (
          await sessionPost("/api/v1/notifications/{notification_id}/read", undefined, {
            ...base,
            pathParams: { notification_id: id },
          })
        ).data,
      readAll: async () => (await sessionPost("/api/v1/notifications/read-all", undefined, base)).data.updated,
      preferences: async () => (await sessionGet("/api/v1/notifications/preferences", base)).data.items,
      setPreference: async (kind, enabled) =>
        (await sessionPut("/api/v1/notifications/preferences", { items: [{ kind, channel: "IN_APP", enabled }] }, base))
          .data.items,
    };
  }, [clinicId]);
}
