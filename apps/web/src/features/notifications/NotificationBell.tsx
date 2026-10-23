"use client";

import Link from "next/link";
import { useEffect, useRef, useState } from "react";

import { Drawer } from "@/components/Drawer";
import { Button } from "@/components/ui/Button";
import { cx } from "@/components/ui/cx";
import { EmptyState } from "@/components/ui/EmptyState";
import { Skeleton } from "@/components/ui/Skeleton";
import { ErrorNotice } from "@/features/auth/ErrorNotice";
import { useSession } from "@/features/auth/SessionProvider";
import { useClinic } from "@/features/shell/ClinicGate";
import { startPolling } from "@/lib/api/poll";
import { formatDateTime } from "@/lib/format/time";

import { useNotificationsApi, type Notification, type NotificationSummary } from "./api";

/** The summary's rhythm (decision 6A): a 304 every 15 s costs next to nothing. */
export const SUMMARY_INTERVAL_MS = 15_000;
export const PREFERENCES_PATH = "/settings/notifications";

type Load =
  | { readonly status: "loading" }
  | { readonly status: "ready"; readonly items: readonly Notification[] }
  | { readonly status: "failed"; readonly error: unknown };

/** "9+" beyond nine, so the badge stays one small circle. */
export function badgeText(unread: number): string {
  return unread > 9 ? "9+" : String(unread);
}

/**
 * The header's notification bell (M6a-P7, decision 6A; FR-NTF-03). The unread count comes from
 * the summary, polled every 15 s with its ETag; the drawer shows the latest 30. Opening one marks
 * it read and goes where it points; *Mark all as read* clears the count. A new arrival is said in
 * a polite live region, never a toast that steals attention. Titles carry nothing clinical.
 */
export function NotificationBell() {
  const api = useNotificationsApi();
  const clinic = useClinic();
  const { endSession } = useSession();
  const [summary, setSummary] = useState<NotificationSummary | undefined>(undefined);
  const [open, setOpen] = useState(false);
  const [announcement, setAnnouncement] = useState("");
  const latest = useRef<string | null | undefined>(undefined);

  useEffect(
    () =>
      startPolling<NotificationSummary>({
        intervalMs: SUMMARY_INTERVAL_MS,
        load: api.summary,
        onData: (next) => {
          // Only an arrival after the first answer is news; the count on load is not.
          if (latest.current !== undefined && next.latest_id !== null && next.latest_id !== latest.current) {
            setAnnouncement(next.unread === 1 ? "1 unread notification" : `${next.unread} unread notifications`);
          }
          latest.current = next.latest_id;
          setSummary(next);
        },
        onError: (error) => {
          endSession(error);
        },
      }),
    [api, endSession],
  );

  const unread = summary?.unread ?? 0;

  return (
    <>
      <Button
        variant="ghost"
        size="sm"
        className="relative"
        aria-haspopup="dialog"
        aria-expanded={open}
        onClick={() => setOpen(true)}
      >
        <BellIcon />
        {/* One text node, so every browser names it "Notifications, 2 unread" exactly. */}
        <span className="sr-only">{unread > 0 ? `Notifications, ${unread} unread` : "Notifications"}</span>
        {unread > 0 && (
          <span
            aria-hidden="true"
            className="absolute -right-1 -top-1 grid min-w-5 place-items-center rounded-full bg-red-700 px-1 text-xs font-semibold text-white"
          >
            {badgeText(unread)}
          </span>
        )}
      </Button>
      <span role="status" aria-live="polite" className="sr-only">
        {announcement}
      </span>
      {open && (
        <NotificationDrawer
          timezone={clinic.timezone}
          onClose={() => setOpen(false)}
          onChanged={(change) => setSummary((s) => (s === undefined ? s : { ...s, unread: Math.max(0, change(s.unread)) }))}
        />
      )}
    </>
  );
}

function NotificationDrawer({
  timezone,
  onClose,
  onChanged,
}: {
  timezone: string;
  onClose: () => void;
  /** Adjusts the badge at once, before the next poll confirms it. */
  onChanged: (change: (unread: number) => number) => void;
}) {
  const api = useNotificationsApi();
  const { endSession } = useSession();
  const [load, setLoad] = useState<Load>({ status: "loading" });
  const [attempt, setAttempt] = useState(0);
  const [actionError, setActionError] = useState<unknown>(null);
  const [message, setMessage] = useState("");

  useEffect(() => {
    let cancelled = false;
    api.list().then(
      (items) => {
        if (!cancelled) setLoad({ status: "ready", items });
      },
      (failure: unknown) => {
        if (!cancelled && !endSession(failure)) setLoad({ status: "failed", error: failure });
      },
    );
    return () => {
      cancelled = true;
    };
  }, [api, attempt, endSession]);

  function openOne(item: Notification) {
    if (item.read_at === null) {
      onChanged((n) => n - 1);
      // The link navigates at once; the read is recorded on the way (a failure only leaves it unread).
      api.read(item.id).catch((failure: unknown) => {
        endSession(failure);
      });
    }
    onClose();
  }

  async function readAll() {
    setActionError(null);
    try {
      await api.readAll();
      const at = new Date().toISOString();
      setLoad((current) =>
        current.status === "ready"
          ? { status: "ready", items: current.items.map((i) => (i.read_at === null ? { ...i, read_at: at } : i)) }
          : current,
      );
      onChanged(() => 0);
      setMessage("All notifications marked as read.");
    } catch (failure) {
      if (!endSession(failure)) setActionError(failure);
    }
  }

  const items = load.status === "ready" ? load.items : [];
  const anyUnread = items.some((i) => i.read_at === null);

  return (
    <Drawer title="Notifications" onClose={onClose}>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <Link href={PREFERENCES_PATH} onClick={onClose} className="font-medium text-brand-800 underline">
          Notification settings
        </Link>
        {anyUnread && (
          <Button size="sm" onClick={() => void readAll()}>
            Mark all as read
          </Button>
        )}
      </div>
      <p role="status" className="sr-only">
        {load.status === "loading" ? "Loading notifications…" : message}
      </p>
      {actionError !== null && <ErrorNotice error={actionError} />}
      {load.status === "loading" && (
        <div className="space-y-2">
          <Skeleton className="h-14" />
          <Skeleton className="h-14" />
        </div>
      )}
      {load.status === "failed" && <ErrorNotice error={load.error} onRetry={() => setAttempt((n) => n + 1)} />}
      {load.status === "ready" && items.length === 0 && (
        <EmptyState title="No notifications yet">
          You are told here when something needs you: a booking with you, an arrival, a message that failed.
        </EmptyState>
      )}
      {items.length > 0 && (
        <ul aria-label="Latest notifications" className="divide-y divide-slate-200 rounded-card border border-slate-200">
          {items.map((item) => {
            const unread = item.read_at === null;
            return (
              <li key={item.id}>
                <Link
                  href={item.link}
                  onClick={() => openOne(item)}
                  className={cx(
                    "flex min-h-12 flex-col gap-0.5 px-4 py-3 hover:bg-slate-50",
                    unread ? "bg-brand-50" : undefined,
                  )}
                >
                  <span className={cx("text-slate-900", unread ? "font-semibold" : undefined)}>
                    {unread && <span className="sr-only">Unread: </span>}
                    {item.title}
                  </span>
                  <span className="text-sm text-slate-700">{formatDateTime(item.created_at, timezone)}</span>
                </Link>
              </li>
            );
          })}
        </ul>
      )}
    </Drawer>
  );
}

function BellIcon() {
  return (
    <svg aria-hidden="true" viewBox="0 0 24 24" className="size-5" fill="none" stroke="currentColor" strokeWidth={2}>
      <path strokeLinecap="round" strokeLinejoin="round" d="M6 8a6 6 0 1 1 12 0c0 7 3 9 3 9H3s3-2 3-9" />
      <path strokeLinecap="round" strokeLinejoin="round" d="M10.3 21a1.94 1.94 0 0 0 3.4 0" />
    </svg>
  );
}
