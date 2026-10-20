"use client";

import { useEffect, useState } from "react";

import { useSession } from "@/features/auth/SessionProvider";
import { useClinic } from "@/features/shell/ClinicGate";

import { useReminderApi, type Reminder } from "./api";
import { ReminderChip } from "./ReminderChip";

/**
 * The reminder of one prescription chain on the consultation (M5-P6 decision 2A): the patient's
 * reminders are loaded and the one for this chain (its version 1) is shown, the latest if there
 * are several. Nothing is shown while loading, without a reminder, or if the load fails: the
 * reminder is a hint here, and the profile has the full list.
 */
export function FollowUpReminder({ patientId, chainId }: Readonly<{ patientId: string; chainId: string }>) {
  const api = useReminderApi();
  const clinic = useClinic();
  const { endSession } = useSession();
  const [reminder, setReminder] = useState<Reminder | undefined>(undefined);

  useEffect(() => {
    let cancelled = false;
    api.list(patientId).then(
      (items) => {
        if (cancelled) return;
        const ours = items.filter((r) => r.prescription_id === chainId);
        setReminder(ours.reduce<Reminder | undefined>((a, b) => (a === undefined || b.created_at > a.created_at ? b : a), undefined));
      },
      (failure: unknown) => {
        if (!cancelled) endSession(failure);
      },
    );
    return () => {
      cancelled = true;
    };
  }, [api, patientId, chainId, endSession]);

  return reminder === undefined ? null : <ReminderChip reminder={reminder} timeZone={clinic.timezone} />;
}
