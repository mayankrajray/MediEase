"use client";

import { ROLE_LABELS } from "@/features/auth/labels";
import type { Membership } from "@/features/auth/landing";

/**
 * Lets a person with several clinics switch between them (spec §6: shown only
 * when there is more than one). A native select: keyboard and screen-reader
 * friendly with nothing to build. The choice applies to this tab.
 */
export function ClinicSwitcher({
  memberships,
  activeClinicId,
  onSelect,
}: {
  memberships: readonly Membership[];
  activeClinicId: string;
  onSelect: (clinicId: string) => void;
}) {
  if (memberships.length < 2) {
    return null;
  }
  return (
    <div className="flex items-center gap-2">
      <label htmlFor="clinic-switcher" className="text-sm font-medium">
        Clinic
      </label>
      <select
        id="clinic-switcher"
        value={activeClinicId}
        onChange={(event) => onSelect(event.target.value)}
        className="rounded-lg border border-slate-400 bg-white px-2 py-1"
      >
        {memberships.map((m) => (
          <option key={m.clinic_id} value={m.clinic_id}>
            {m.clinic_name} ({ROLE_LABELS[m.role]})
          </option>
        ))}
      </select>
    </div>
  );
}
