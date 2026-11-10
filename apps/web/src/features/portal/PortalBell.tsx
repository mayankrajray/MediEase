"use client";

import { Bell } from "lucide-react";
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
        prefetch={false}
        className="relative inline-flex min-h-11 min-w-11 items-center justify-center rounded-full text-slate-900 transition-colors duration-200 ease-brand hover:bg-slate-100 motion-reduce:transition-none"
      >
        <Bell aria-hidden="true" className="size-[1.375rem]" strokeWidth={1.75} />
        <span className="sr-only">{words.bell(unread)}</span>
        {unread > 0 && (
          <span
            aria-hidden="true"
            className="absolute right-0.5 top-0.5 grid h-5 min-w-5 place-items-center rounded-full bg-red-700 px-1 text-xs font-semibold tabular-nums text-white ring-2 ring-white"
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
