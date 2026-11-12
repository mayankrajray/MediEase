"use client";

import { useEffect, useState } from "react";

import { Alert } from "@/components/ui/Alert";
import { Card } from "@/components/ui/Card";
import { CheckboxField } from "@/components/ui/Field";
import { PageHeader } from "@/components/ui/PageHeader";
import { Skeleton } from "@/components/ui/Skeleton";
import { ErrorNotice } from "@/features/auth/ErrorNotice";
import { useSession } from "@/features/auth/SessionProvider";
import { DevicePush } from "@/features/pwa/DevicePush";
import { deviceWords } from "@/lib/i18n/push";

import { useNotificationsApi, type Preference } from "./api";

const DEVICE = deviceWords("en");
// The in-app switches keep their M6a ids; the push ones are told apart by a prefix.
const CHANNELS = [
  { channel: "IN_APP", legend: "In the app", prefix: "" },
  { channel: "PUSH", legend: "Pop-up alerts", prefix: "push-" },
] as const;

type Load =
  | { readonly status: "loading" }
  | { readonly status: "ready"; readonly items: readonly Preference[] }
  | { readonly status: "failed"; readonly error: unknown };

/**
 * My notification settings (M6a-P7, decision 5A; FR-NTF-05): one switch per kind, every one on
 * until you turn it off. Each change saves at once and says so. Patients' WhatsApp messages follow
 * their consent on their profile, not these switches. M7e-E5 (spec web-push R50-R54): pop-up
 * alerts on this device, and a second set of switches for which kinds alert.
 */
export function NotificationPreferences() {
  const api = useNotificationsApi();
  const { endSession } = useSession();
  const [load, setLoad] = useState<Load>({ status: "loading" });
  const [attempt, setAttempt] = useState(0);
  const [saving, setSaving] = useState<string | undefined>(undefined);
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
    setSaving(`${item.kind}:${item.channel}`);
    setError(null);
    setMessage("");
    try {
      const items = await api.setPreference(item.kind, enabled, item.channel);
      setLoad({ status: "ready", items });
      const state = enabled ? "on" : "off";
      setMessage(
        item.channel === "PUSH"
          ? `Saved: the pop-up alert for “${item.label}” is ${state}.`
          : `Saved: “${item.label}” is ${state}.`,
      );
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
        description="Choose what you are told about, in the app and as pop-up alerts. Everything is on until you turn it off."
      />
      {message !== "" && load.status !== "loading" ? (
        // M7c-P7 (M3): the saved change in the success tone, beside the switches it describes.
        <Alert tone="success" role="status">
          {message}
        </Alert>
      ) : (
        <p role="status" className="sr-only">
          {load.status === "loading" ? "Loading your notification settings…" : ""}
        </p>
      )}
      {error !== null && <ErrorNotice error={error} />}
      <Card>
        <h2 className="mb-2 font-semibold text-slate-900">{DEVICE.title}</h2>
        <DevicePush owner="staff" words={DEVICE} api={api.push} onSessionError={endSession} onSaved={setMessage} />
      </Card>
      {load.status === "loading" && <Skeleton className="h-96" />}
      {load.status === "failed" && <ErrorNotice error={load.error} onRetry={() => setAttempt((n) => n + 1)} />}
      {load.status === "ready" && (
        <Card>
          <div className="grid gap-6 md:grid-cols-2">
            {CHANNELS.map(({ channel, legend, prefix }) => (
              <fieldset key={channel} className="space-y-2" disabled={saving !== undefined}>
                <legend className="mb-2 font-semibold text-slate-900">{legend}</legend>
                {load.items
                  .filter((item) => item.channel === channel)
                  .map((item) => (
                    <CheckboxField
                      key={item.kind}
                      id={`notify-${prefix}${item.kind.replace(".", "-")}`}
                      label={item.label}
                      checked={item.enabled}
                      onChange={(enabled) => void change(item, enabled)}
                    />
                  ))}
              </fieldset>
            ))}
          </div>
          <p className="mt-4 text-sm text-slate-700">
            Patients get WhatsApp messages only with their consent, which is recorded on their profile.
          </p>
        </Card>
      )}
    </section>
  );
}
