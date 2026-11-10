"use client";

import { Bell, CheckCheck, Settings } from "lucide-react";
import Link from "next/link";
import { useState } from "react";

import { Button } from "@/components/ui/Button";
import { EmptyState } from "@/components/ui/EmptyState";
import { ErrorNotice } from "@/features/auth/ErrorNotice";
import { portalGet, portalPost } from "@/lib/auth/portal-session";
import { notificationWords } from "@/lib/i18n/patient-notifications";
import { portalDay, portalTime } from "@/lib/i18n/portal";

import { DEFAULT_ZONE, type PortalNotification, usePortalLoad } from "./data";
import { PORTAL_LINK, PortalTitle, ScreenLoading, usePortal } from "./PortalShell";

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
        <PortalTitle>{words.title}</PortalTitle>
        {anyUnread && (
          <Button onClick={() => void readAll()} icon={<CheckCheck className="size-4" />} className="min-h-11">
            {words.markAll}
          </Button>
        )}
      </div>
      <p role="status" className="min-h-0 font-medium text-success empty:sr-only">
        {status}
      </p>
      {error !== null && <ErrorNotice error={error} />}
      {loaded.status === "loading" && <ScreenLoading label={s.loading} />}
      {loaded.status === "failed" && <ErrorNotice error={loaded.error} onRetry={loaded.retry} />}
      {loaded.status === "ready" && items.length === 0 && <EmptyState title={words.emptyTitle} icon={<Bell className="size-5" />}>{words.empty}</EmptyState>}
      {items.length > 0 && (
        <ul aria-label={words.title} className="divide-y divide-line overflow-hidden rounded-card border border-line bg-white shadow-card">
          {items.map((n) => {
            const unread = isUnread(n);
            return (
              <li key={n.id}>
                <Link
                  href={n.link}
                  onClick={() => openOne(n)}
                  className={`flex min-h-16 items-start gap-3 px-4 py-3 transition-colors duration-200 ease-brand hover:bg-slate-50 motion-reduce:transition-none ${unread ? "bg-brand-50/70" : ""}`}
                >
                  <span
                    aria-hidden="true"
                    className={`mt-0.5 grid size-9 shrink-0 place-items-center rounded-full ${unread ? "bg-brand-700 text-white" : "bg-slate-100 text-slate-600"}`}
                  >
                    <Bell className="size-4" />
                  </span>
                  <span className="flex min-w-0 flex-1 flex-col gap-0.5">
                    <span className={`[overflow-wrap:anywhere] ${unread ? "font-semibold text-slate-900" : "text-slate-900"}`}>
                      {unread && <span className="sr-only">{words.unread}</span>}
                      {n.title}
                    </span>
                    <span className="text-sm text-slate-700">
                      {portalDay(n.created_at, DEFAULT_ZONE, s)}, {portalTime(n.created_at, DEFAULT_ZONE, s)}
                    </span>
                  </span>
                  {unread && <span aria-hidden="true" className="mt-2 size-2.5 shrink-0 rounded-full bg-brand-600" />}
                </Link>
              </li>
            );
          })}
        </ul>
      )}
      <Link href="/portal/account#notifications-heading" className={PORTAL_LINK}>
        <Settings aria-hidden="true" className="size-4" />
        {words.settings}
      </Link>
    </div>
  );
}
