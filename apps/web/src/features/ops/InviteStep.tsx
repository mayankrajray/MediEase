"use client";

import { useRef, useState, type FormEvent } from "react";

import { CheckboxField, SelectField, TextField } from "@/components/ui/Field";
import { useFocusOnError } from "@/components/useFocusOnError";
import { ErrorNotice } from "@/features/auth/ErrorNotice";
import { ROLE_LABELS } from "@/features/auth/labels";
import type { Role } from "@/features/auth/landing";
import { useSession } from "@/features/auth/SessionProvider";
import type { PostResponse } from "@/lib/api/client";
import { fieldErrors } from "@/lib/api/field-errors";
import { sessionPost } from "@/lib/auth/refresh";

import { AcceptLink } from "./AcceptLink";
import type { AddedDoctor } from "./DoctorsStep";
import { emptyToNull } from "./fields";

const PATH = "/api/v1/ops/clinics/{clinic_id}/staff-invites" as const;
const ROLES: readonly Role[] = ["OWNER", "DOCTOR", "FRONT_DESK"];

export type Invitation = PostResponse<typeof PATH>;
/** What the lists show about someone invited; their link is gone (shown once). */
export type InvitedPerson = Pick<Invitation, "membership_id" | "full_name" | "role">;

const NEEDS_CONTACT = "Enter an email address or a phone number: it is how they sign in.";

/**
 * Step 3: invite the owner, and anyone else, by email or phone
 * (`POST /ops/clinics/{id}/staff-invites`). The response carries the one and only
 * copy of the acceptance link; it is shown until the person moves on.
 */
export function InviteStep({
  clinicId,
  doctors = [],
  invited,
  onInvited,
  onFinish,
}: {
  clinicId: string;
  /**
   * Doctors added in step 2 (M6a-P6, decision 8A): an owner who also practises is linked to
   * one of them, Doctor 1 by default, in the same invitation.
   */
  doctors?: readonly AddedDoctor[];
  /** People invited so far (their links are gone: they are shown once). */
  invited: readonly InvitedPerson[];
  onInvited: (invitation: Invitation) => void;
  onFinish: () => void;
}) {
  const { endSession } = useSession();
  const [fullName, setFullName] = useState("");
  const [role, setRole] = useState<Role>("OWNER");
  const [email, setEmail] = useState("");
  const [phone, setPhone] = useState("");
  const linkable = doctors.filter((d) => d.is_active && d.user_id === null);
  const [practises, setPractises] = useState(false);
  const [doctorId, setDoctorId] = useState(linkable[0]?.id ?? "");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [missingContact, setMissingContact] = useState(false);
  const [latest, setLatest] = useState<Invitation | null>(null);
  const container = useRef<HTMLDivElement>(null);
  useFocusOnError(error ?? (missingContact ? "contact" : null), container);

  const problems = fieldErrors(error);
  const alertError = error !== null && Object.keys(problems).length === 0;
  const contactError = missingContact ? NEEDS_CONTACT : undefined;

  async function onSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (submitting) return;
    if (email.trim() === "" && phone.trim() === "") {
      setMissingContact(true);
      return;
    }
    setMissingContact(false);
    setSubmitting(true);
    setError(null);
    try {
      const { data } = await sessionPost(
        PATH,
        {
          full_name: fullName.trim(),
          role,
          email: emptyToNull(email),
          phone: emptyToNull(phone),
          ...(role === "OWNER" && practises && doctorId !== "" ? { doctor_id: doctorId } : {}),
        },
        { pathParams: { clinic_id: clinicId } },
      );
      setLatest(data);
      onInvited(data);
    } catch (failure) {
      if (!endSession(failure)) setError(failure);
    } finally {
      setSubmitting(false);
    }
  }

  function inviteAnother() {
    setLatest(null);
    setFullName("");
    setEmail("");
    setPhone("");
    setRole("DOCTOR");
    setPractises(false);
  }

  if (latest !== null) {
    return (
      <div className="max-w-2xl space-y-4">
        <p role="status">
          Invitation created for <strong>{latest.full_name}</strong> as {ROLE_LABELS[latest.role]}.
        </p>
        <AcceptLink url={latest.accept_url} name={latest.full_name} />
        <div className="flex flex-wrap gap-3">
          <button
            type="button"
            onClick={inviteAnother}
            className="rounded-lg border border-brand-700 px-4 py-2 font-semibold text-brand-800 hover:bg-brand-50"
          >
            Invite another person
          </button>
          <button
            type="button"
            onClick={onFinish}
            className="inline-flex min-h-10 items-center justify-center gap-2 rounded-lg bg-brand-700 px-4 py-2 font-medium text-white transition-colors hover:bg-brand-800 disabled:cursor-not-allowed disabled:bg-slate-400 motion-reduce:transition-none"
          >
            Finish
          </button>
        </div>
        <p className="text-sm text-slate-700">
          Copy the link before you continue: it cannot be shown again.
        </p>
      </div>
    );
  }

  return (
    <div ref={container} className="max-w-2xl space-y-5">
      {invited.length > 0 && (
        <section aria-labelledby="invited-so-far">
          <h3 id="invited-so-far" className="font-semibold">
            Invited so far ({invited.length})
          </h3>
          <ul className="list-disc pl-6">
            {invited.map((person) => (
              <li key={person.membership_id}>
                {person.full_name}, {ROLE_LABELS[person.role]}
              </li>
            ))}
          </ul>
        </section>
      )}

      {alertError && <ErrorNotice error={error} />}
      <form onSubmit={(event) => void onSubmit(event)} className="space-y-4" noValidate>
        <TextField
          id="invite-name"
          label="Full name"
          required
          maxLength={200}
          value={fullName}
          error={problems["full_name"]}
          onChange={setFullName}
        />
        <div className="space-y-1">
          <label htmlFor="invite-role" className="block font-medium">
            Role
          </label>
          <select
            id="invite-role"
            value={role}
            onChange={(event) => setRole(event.target.value as Role)}
            className="rounded-lg border border-slate-400 bg-white px-3 py-2"
          >
            {ROLES.map((value) => (
              <option key={value} value={value}>
                {ROLE_LABELS[value]}
              </option>
            ))}
          </select>
        </div>
        <TextField
          id="invite-email"
          label="Email"
          type="email"
          inputMode="email"
          maxLength={254}
          value={email}
          error={problems["email"] ?? contactError}
          onChange={setEmail}
        />
        <TextField
          id="invite-phone"
          label="Phone"
          type="tel"
          inputMode="tel"
          maxLength={20}
          hint="A 10-digit Indian number is fine. Needed if there is no email."
          value={phone}
          error={problems["phone"]}
          onChange={setPhone}
        />
        {role === "OWNER" && linkable.length > 0 && (
          <div className="space-y-3 rounded-lg border border-slate-300 p-3">
            <CheckboxField
              id="invite-practises"
              label="The owner also practises here"
              hint="Their invitation links them to a doctor added in step 2, so they can switch between the Owner and Doctor views."
              checked={practises}
              onChange={setPractises}
            />
            {practises && (
              <SelectField
                id="invite-doctor"
                label="Which doctor is the owner?"
                value={doctorId}
                error={problems["doctor_id"]}
                options={linkable.map((d, i) => ({
                  value: d.id,
                  label: `${d.display_name}${i === 0 ? " (Doctor 1)" : ""}`,
                }))}
                onChange={setDoctorId}
              />
            )}
          </div>
        )}
        <button
          type="submit"
          disabled={submitting}
          className="inline-flex min-h-10 items-center justify-center gap-2 rounded-lg bg-brand-700 px-4 py-2 font-medium text-white transition-colors hover:bg-brand-800 disabled:cursor-not-allowed disabled:bg-slate-400 motion-reduce:transition-none"
        >
          {submitting ? "Inviting…" : "Create invitation"}
        </button>
      </form>

      {invited.length > 0 && (
        <div className="border-t border-slate-300 pt-4">
          <button
            type="button"
            onClick={onFinish}
            className="rounded-lg border border-slate-400 px-4 py-2 font-medium hover:bg-slate-100"
          >
            Finish without inviting anyone else
          </button>
        </div>
      )}
    </div>
  );
}
