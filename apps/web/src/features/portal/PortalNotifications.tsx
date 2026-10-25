"use client";

import Link from "next/link";
import { useState } from "react";

import { ErrorNotice } from "@/features/auth/ErrorNotice";
import { portalGet, portalPost } from "@/lib/auth/portal-session";
import { notificationWords } from "@/lib/i18n/patient-notifications";
import { portalDay, portalTime } from "@/lib/i18n/portal";

import { DEFAULT_ZONE, type PortalNotification, usePortalLoad } from "./data";
import { ScreenLoading, usePortal } from "./PortalShell";

async function loadNotifications(): Promise<readonly PortalNotification[]> {
  return (await portalGet("/api/v1/portal/notifications")).data.items;
}

/**
 * *Notifications* (M6b-P6; spec R55, R67, R68): the newest 50, unread first in weight, each
 * opening where it points and marking itself read on the way; *Mark all as read*. The titles come
 * from the API in the account's language and carry nothing clinical (R59).
 */
export function PortalNotifications() {
  const { s, leave, refreshBell } = usePortal();
  const words = notificationWords(s.lang);
  const loaded = usePortalLoad(loadNotifications);
  const [readIds, setReadIds] = useState<ReadonlySet<string>>(new Set());
  const [allRead, setAllRead] = useState(false);
  const [status, setStatus] = useState("");
  const [error, setError] = useState<unknown>(null);

  const items = loaded.status === "ready" ? loaded.data : [];
  const isUnread = (n: PortalNotification) => n.read_at === null && !allRead && !readIds.has(n.id);
  const anyUnread = items.some(isUnread);

  function openOne(n: PortalNotification) {
    if (!isUnread(n)) return;
    setReadIds((old) => new Set([...old, n.id]));
    // The link navigates at once; the read is recorded on the way (a failure only leaves it unread).
    portalPost("/api/v1/portal/notifications/{notification_id}/read", undefined, { pathParams: { notification_id: n.id } }).then(
      refreshBell,
      (failure: unknown) => {
        leave(failure);
      },
    );
  }

  async function readAll() {
    setError(null);
    try {
      await portalPost("/api/v1/portal/notifications/read-all", undefined);
      setAllRead(true);
      setStatus(words.allRead);
      refreshBell();
    } catch (failure) {
      if (!leave(failure)) setError(failure);
    }
  }

  return (
    <div className="space-y-5">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-2xl font-bold tracking-tight">{words.title}</h1>
        {anyUnread && (
          <button
            type="button"
            onClick={() => void readAll()}
            className="inline-flex min-h-11 items-center rounded-lg bg-brand-700 px-4 font-semibold text-white hover:bg-brand-800"
          >
            {words.markAll}
          </button>
        )}
      </div>
      <p role="status" className="min-h-6">
        {status}
      </p>
      {error !== null && <ErrorNotice error={error} />}
      {loaded.status === "loading" && <ScreenLoading label={s.loading} />}
      {loaded.status === "failed" && <ErrorNotice error={loaded.error} onRetry={loaded.retry} />}
      {loaded.status === "ready" && items.length === 0 && <p>{words.empty}</p>}
      {items.length > 0 && (
        <ul aria-label={words.title} className="divide-y divide-slate-200 rounded-card border border-slate-200 bg-white">
          {items.map((n) => {
            const unread = isUnread(n);
            return (
              <li key={n.id}>
                <Link
                  href={n.link}
                  onClick={() => openOne(n)}
                  className={`flex min-h-14 flex-col gap-0.5 px-4 py-3 hover:bg-slate-50 ${unread ? "bg-brand-50" : ""}`}
                >
                  <span className={unread ? "font-semibold text-slate-900" : "text-slate-900"}>
                    {unread && <span className="sr-only">{words.unread}</span>}
                    {n.title}
                  </span>
                  <span className="text-sm text-slate-700">
                    {portalDay(n.created_at, DEFAULT_ZONE, s)}, {portalTime(n.created_at, DEFAULT_ZONE, s)}
                  </span>
                </Link>
              </li>
            );
          })}
        </ul>
      )}
      <Link href="/portal/account#notifications-heading" className="inline-flex min-h-11 items-center font-medium text-brand-800 underline">
        {words.settings}
      </Link>
    </div>
  );
}
