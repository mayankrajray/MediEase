"use client";

import { useEffect, useState } from "react";

import { Card } from "@/components/ui/Card";
import { CheckboxField } from "@/components/ui/Field";
import { PageHeader } from "@/components/ui/PageHeader";
import { Skeleton } from "@/components/ui/Skeleton";
import { ErrorNotice } from "@/features/auth/ErrorNotice";
import { useSession } from "@/features/auth/SessionProvider";

import { useNotificationsApi, type NotificationKind, type Preference } from "./api";

type Load =
  | { readonly status: "loading" }
  | { readonly status: "ready"; readonly items: readonly Preference[] }
  | { readonly status: "failed"; readonly error: unknown };

/**
 * My notification settings (M6a-P7, decision 5A; FR-NTF-05): one switch per kind, in the app
 * only, every one on until you turn it off. Each change saves at once and says so. Patients'
 * WhatsApp messages follow their consent on their profile, not these switches.
 */
export function NotificationPreferences() {
  const api = useNotificationsApi();
  const { endSession } = useSession();
  const [load, setLoad] = useState<Load>({ status: "loading" });
  const [attempt, setAttempt] = useState(0);
  const [saving, setSaving] = useState<NotificationKind | undefined>(undefined);
  const [error, setError] = useState<unknown>(null);
  const [message, setMessage] = useState("");

  useEffect(() => {
    let cancelled = false;
    api.preferences().then(
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

  async function change(item: Preference, enabled: boolean) {
    if (saving !== undefined) return;
    setSaving(item.kind);
    setError(null);
    setMessage("");
    try {
      const items = await api.setPreference(item.kind, enabled);
      setLoad({ status: "ready", items });
      setMessage(`Saved: “${item.label}” is ${enabled ? "on" : "off"}.`);
    } catch (failure) {
      if (!endSession(failure)) setError(failure);
    } finally {
      setSaving(undefined);
    }
  }

  return (
    <section className="space-y-4">
      <PageHeader
        title="Notifications"
        description="Choose what you are told about in the app. Everything is on until you turn it off."
      />
      <p role="status" className={load.status === "loading" || message === "" ? "sr-only" : "text-slate-800"}>
        {load.status === "loading" ? "Loading your notification settings…" : message}
      </p>
      {error !== null && <ErrorNotice error={error} />}
      {load.status === "loading" && <Skeleton className="h-48" />}
      {load.status === "failed" && <ErrorNotice error={load.error} onRetry={() => setAttempt((n) => n + 1)} />}
      {load.status === "ready" && (
        <Card>
          <fieldset className="space-y-2" disabled={saving !== undefined}>
            <legend className="mb-2 font-semibold text-slate-900">In the app</legend>
            {load.items.map((item) => (
              <CheckboxField
                key={item.kind}
                id={`notify-${item.kind.replace(".", "-")}`}
                label={item.label}
                checked={item.enabled}
                onChange={(enabled) => void change(item, enabled)}
              />
            ))}
          </fieldset>
          <p className="mt-4 text-sm text-slate-700">
            Patients get WhatsApp messages only with their consent, which is recorded on their profile.
          </p>
        </Card>
      )}
    </section>
  );
}
