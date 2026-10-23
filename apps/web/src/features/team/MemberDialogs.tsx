"use client";

import { useEffect, useState } from "react";

import { Dialog } from "@/components/Dialog";
import { Button } from "@/components/ui/Button";
import { SelectField } from "@/components/ui/Field";
import { ErrorNotice } from "@/features/auth/ErrorNotice";
import { ROLE_LABELS } from "@/features/auth/labels";
import type { Role } from "@/features/auth/landing";
import { useSession } from "@/features/auth/SessionProvider";
import { AcceptLink } from "@/features/ops/AcceptLink";

import { useTeamApi, type ClinicDoctor, type StaffMember, type TeamInvitation } from "./api";
import { ROLE_HINTS, ROLES } from "./labels";

/**
 * Change a member's role (decision 4A). The API's last-owner refusal is shown as it is; an owner
 * moving themselves off Owner is warned first that they will lose this page.
 */
export function ChangeRoleDialog({
  member,
  isYou,
  onChanged,
  onClose,
}: {
  member: StaffMember;
  isYou: boolean;
  onChanged: (member: StaffMember) => void;
  onClose: () => void;
}) {
  const api = useTeamApi();
  const { endSession } = useSession();
  const [role, setRole] = useState<Role>(member.role);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const losesTeam = isYou && member.role === "OWNER" && role !== "OWNER";

  async function save() {
    if (saving) return;
    setSaving(true);
    setError(null);
    try {
      onChanged(await api.changeRole(member.membership_id, role));
    } catch (failure) {
      if (!endSession(failure)) setError(failure);
    } finally {
      setSaving(false);
    }
  }

  return (
    <Dialog title={`Change ${member.full_name}'s role`} onClose={onClose}>
      <fieldset className="space-y-2">
        <legend className="font-medium">Role</legend>
        {ROLES.map((value) => (
          <label key={value} className="flex items-start gap-3 rounded-lg border border-slate-300 p-3 has-[:checked]:border-brand-700">
            <input
              type="radio"
              name="team-role"
              value={value}
              checked={role === value}
              onChange={() => setRole(value)}
              className="mt-1 size-4"
              {...(value === member.role ? { "data-autofocus": true } : {})}
            />
            <span>
              <span className="block font-medium">{ROLE_LABELS[value]}</span>
              <span className="block text-sm text-slate-700">{ROLE_HINTS[value]}</span>
            </span>
          </label>
        ))}
      </fieldset>
      {losesTeam && (
        <p className="rounded-lg border border-amber-400 bg-amber-50 p-3 text-amber-950">
          You are changing your own role. You will lose this Team page and the clinic settings as soon as you save.
        </p>
      )}
      {error !== null && <ErrorNotice error={error} />}
      <div className="flex flex-wrap gap-2">
        <Button variant="primary" disabled={saving || role === member.role} onClick={() => void save()}>
          {saving ? "Saving…" : "Save role"}
        </Button>
        <Button onClick={onClose}>Cancel</Button>
      </div>
    </Dialog>
  );
}

/** Deactivate behind a confirmation that says what happens (decision 5A). */
export function DeactivateDialog({
  member,
  onDeactivated,
  onClose,
}: {
  member: StaffMember;
  onDeactivated: (member: StaffMember) => void;
  onClose: () => void;
}) {
  const api = useTeamApi();
  const { endSession } = useSession();
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<unknown>(null);

  async function confirm() {
    if (saving) return;
    setSaving(true);
    setError(null);
    try {
      onDeactivated(await api.deactivate(member.membership_id));
    } catch (failure) {
      if (!endSession(failure)) setError(failure);
    } finally {
      setSaving(false);
    }
  }

  return (
    <Dialog title={`Deactivate ${member.full_name}?`} onClose={onClose}>
      <p>
        {member.status === "INVITED"
          ? "Their invitation link stops working at once."
          : "They are signed out of this clinic on their next click and can no longer work here."}{" "}
        They stay in the list with their history, and you can invite them back later.
      </p>
      {error !== null && <ErrorNotice error={error} />}
      <div className="flex flex-wrap gap-2">
        <Button variant="danger" disabled={saving} onClick={() => void confirm()}>
          {saving ? "Deactivating…" : "Deactivate"}
        </Button>
        <Button onClick={onClose} data-autofocus>
          Cancel
        </Button>
      </div>
    </Dialog>
  );
}

/** A resent phone-only invitation: its new link, shown once. */
export function LinkDialog({ invitation, onClose }: { invitation: TeamInvitation; onClose: () => void }) {
  return (
    <Dialog title={`New invitation link for ${invitation.full_name}`} onClose={onClose}>
      {invitation.accept_url !== null && <AcceptLink url={invitation.accept_url} name={invitation.full_name} />}
      <Button variant="primary" onClick={onClose}>
        Done
      </Button>
    </Dialog>
  );
}

/**
 * Link a doctor profile to an active member (M6a-P6, decision 8A), the owner included: "I also
 * practise here". Lists the clinic's active profiles that no one is linked to yet.
 */
export function LinkDoctorDialog({
  member,
  isYou,
  onLinked,
  onClose,
}: {
  member: StaffMember;
  isYou: boolean;
  onLinked: (member: StaffMember) => void;
  onClose: () => void;
}) {
  const api = useTeamApi();
  const { endSession } = useSession();
  const [doctors, setDoctors] = useState<readonly ClinicDoctor[] | undefined>(undefined);
  const [doctorId, setDoctorId] = useState("");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<unknown>(null);

  useEffect(() => {
    let cancelled = false;
    api.doctors().then(
      (items) => {
        if (cancelled) return;
        const free = items.filter((d) => d.is_active && d.user_id === null);
        setDoctors(free);
        setDoctorId(free[0]?.id ?? "");
      },
      (failure: unknown) => {
        if (!cancelled && !endSession(failure)) setError(failure);
      },
    );
    return () => {
      cancelled = true;
    };
  }, [api, endSession]);

  async function save() {
    if (saving || doctorId === "") return;
    setSaving(true);
    setError(null);
    try {
      await api.linkDoctor(doctorId, member.user_id);
      onLinked({ ...member, has_doctor_profile: true });
    } catch (failure) {
      if (!endSession(failure)) setError(failure);
    } finally {
      setSaving(false);
    }
  }

  return (
    <Dialog title={isYou ? "I also practise here" : `Link a doctor profile to ${member.full_name}`} onClose={onClose}>
      <p>
        {isYou
          ? "Link yourself to your doctor profile: you can then switch between the Owner and Doctor views, and write consultations and prescriptions."
          : "They will see their own patients and sessions, and can write consultations and prescriptions."}
      </p>
      {doctors === undefined && error === null && <p role="status">Loading the doctors…</p>}
      {doctors !== undefined && doctors.length === 0 && (
        <p>Every doctor profile is already linked. Add the doctor in the clinic settings first.</p>
      )}
      {doctors !== undefined && doctors.length > 0 && (
        <SelectField
          id="team-link-doctor"
          label="Doctor profile"
          value={doctorId}
          options={doctors.map((d) => ({ value: d.id, label: `${d.display_name} · ${d.registration_number}` }))}
          onChange={setDoctorId}
        />
      )}
      {error !== null && <ErrorNotice error={error} />}
      <div className="flex flex-wrap gap-2">
        <Button variant="primary" disabled={saving || doctorId === ""} onClick={() => void save()}>
          {saving ? "Linking…" : "Link profile"}
        </Button>
        <Button onClick={onClose}>Cancel</Button>
      </div>
    </Dialog>
  );
}
