"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";

import { startPolling } from "@/lib/api/poll";
import { portalGetConditional } from "@/lib/auth/portal-session";
import { notificationWords } from "@/lib/i18n/patient-notifications";
import type { PortalLanguage } from "@/lib/i18n/portal";

import type { PortalNotificationSummary } from "./data";

/** R67: the bell's rhythm; a 304 every 30 s costs next to nothing. */
export const PORTAL_SUMMARY_INTERVAL_MS = 30_000;
export const PORTAL_NOTIFICATIONS_PATH = "/portal/notifications";

/** "9+" beyond nine, so the badge stays one small circle. */
export function portalBadge(unread: number): string {
  return unread > 9 ? "9+" : String(unread);
}

/**
 * The portal header's bell (M6b-P6; spec R67): the unread count from the summary, polled every
 * 30 s with its ETag while the tab is visible; it opens *Notifications*. A new arrival is said in
 * a polite live region, never a pop-up. `tick` changes when a screen has just marked some read,
 * which polls again at once.
 */
export function PortalBell({
  language,
  tick,
  onEnded,
}: Readonly<{ language: PortalLanguage; tick: number; onEnded: (error: unknown) => boolean }>) {
  const words = notificationWords(language);
  const [summary, setSummary] = useState<PortalNotificationSummary | undefined>(undefined);
  const [announcement, setAnnouncement] = useState("");
  const latest = useRef<string | null | undefined>(undefined);
  const ended = useRef(onEnded);
  useEffect(() => {
    ended.current = onEnded;
  }, [onEnded]);

  useEffect(
    () =>
      startPolling<PortalNotificationSummary>({
        intervalMs: PORTAL_SUMMARY_INTERVAL_MS,
        load: (etag, signal) => portalGetConditional("/api/v1/portal/notifications/summary", etag, { signal }),
        onData: (next) => {
          // Only an arrival after the first answer is news; the count on load is not.
          if (latest.current !== undefined && next.latest_id !== null && next.latest_id !== latest.current) {
            setAnnouncement(notificationWords(language).arrived(next.unread));
          }
          latest.current = next.latest_id;
          setSummary(next);
        },
        onError: (error) => {
          ended.current(error);
        },
      }),
    [language, tick],
  );

  const unread = summary?.unread ?? 0;
  return (
    <>
      <Link
        href={PORTAL_NOTIFICATIONS_PATH}
        className="relative inline-flex min-h-11 min-w-11 items-center justify-center rounded-lg text-slate-900 hover:bg-slate-100"
      >
        <BellIcon />
        <span className="sr-only">{words.bell(unread)}</span>
        {unread > 0 && (
          <span
            aria-hidden="true"
            className="absolute right-0 top-0 grid min-w-5 place-items-center rounded-full bg-red-700 px-1 text-xs font-semibold text-white"
          >
            {portalBadge(unread)}
          </span>
        )}
      </Link>
      {/* A live region without the status role: each screen keeps its own one status message. */}
      <span aria-live="polite" aria-atomic="true" className="sr-only">
        {announcement}
      </span>
    </>
  );
}

function BellIcon() {
  return (
    <svg aria-hidden="true" viewBox="0 0 24 24" className="size-6" fill="none" stroke="currentColor" strokeWidth={2}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M6 8a6 6 0 1 1 12 0c0 7 3 9 3 9H3s3-2 3-9" />
      <path strokeLinecap="round" strokeLinejoin="round" d="M10.3 21a1.94 1.94 0 0 0 3.4 0" />
    </svg>
  );
}
