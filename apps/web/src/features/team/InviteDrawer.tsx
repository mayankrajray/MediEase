"use client";

import { useRef, useState, type FormEvent } from "react";

import { Drawer } from "@/components/Drawer";
import { Button } from "@/components/ui/Button";
import { SelectField, TextField } from "@/components/ui/Field";
import { useFocusOnError } from "@/components/useFocusOnError";
import { ErrorNotice } from "@/features/auth/ErrorNotice";
import { ROLE_LABELS } from "@/features/auth/labels";
import type { Role } from "@/features/auth/landing";
import { useSession } from "@/features/auth/SessionProvider";
import { AcceptLink } from "@/features/ops/AcceptLink";
import { emptyToNull } from "@/features/ops/fields";
import { fieldErrors } from "@/lib/api/field-errors";

import { useTeamApi, type StaffMember, type TeamInvitation } from "./api";
import { ROLE_HINTS, ROLES } from "./labels";

const NEEDS_CONTACT = "Enter an email address or a phone number: it is how they sign in.";

/**
 * Invite somebody, or bring a deactivated member back (decisions 3A and 6A). With an email
 * address the invitation is emailed and no link is ever shown; phone only, the link is shown once
 * here to share on WhatsApp.
 */
export function InviteDrawer({
  again,
  onInvited,
  onClose,
}: {
  /** A deactivated member to invite back: their name and contact are filled in. */
  again?: StaffMember;
  onInvited: (invitation: TeamInvitation) => void;
  onClose: () => void;
}) {
  const api = useTeamApi();
  const { endSession } = useSession();
  const [fullName, setFullName] = useState(again?.full_name ?? "");
  const [role, setRole] = useState<Role>(again?.role ?? "FRONT_DESK");
  const [email, setEmail] = useState(again?.email ?? "");
  const [phone, setPhone] = useState(again?.phone_e164 ?? "");
  const [submitting, setSubmitting] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [missingContact, setMissingContact] = useState(false);
  const [link, setLink] = useState<TeamInvitation | null>(null);
  const container = useRef<HTMLDivElement>(null);
  useFocusOnError(error ?? (missingContact ? "contact" : null), container);

  const problems = fieldErrors(error);
  const alertError = error !== null && Object.keys(problems).length === 0;
  const title = again === undefined ? "Invite someone" : `Invite ${again.full_name} back`;

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
      const invitation = await api.invite({
        full_name: fullName.trim(),
        role,
        email: emptyToNull(email),
        phone: emptyToNull(phone),
      });
      onInvited(invitation);
      if (invitation.accept_url !== null) setLink(invitation);
      else onClose();
    } catch (failure) {
      if (!endSession(failure)) setError(failure);
    } finally {
      setSubmitting(false);
    }
  }

  if (link !== null && link.accept_url !== null) {
    return (
      <Drawer title={title} onClose={onClose}>
        <p role="status">
          Invitation created for <strong>{link.full_name}</strong> as {ROLE_LABELS[link.role]}. They have no email
          address, so share this link with them, for example on WhatsApp.
        </p>
        <AcceptLink url={link.accept_url} name={link.full_name} />
        <Button variant="primary" onClick={onClose}>
          Done
        </Button>
      </Drawer>
    );
  }

  return (
    <Drawer title={title} onClose={onClose}>
      <div ref={container} className="space-y-4">
        {again !== undefined && (
          <p className="text-slate-800">
            They keep their account and their history here, and become active again once they accept.
          </p>
        )}
        {alertError && <ErrorNotice error={error} />}
        <form onSubmit={(event) => void onSubmit(event)} className="space-y-4" noValidate>
          <TextField
            id="team-invite-name"
            label="Full name"
            required
            maxLength={200}
            value={fullName}
            error={problems["full_name"]}
            onChange={setFullName}
          />
          <SelectField
            id="team-invite-role"
            label="Role"
            value={role}
            hint={ROLE_HINTS[role]}
            options={ROLES.map((value) => ({ value, label: ROLE_LABELS[value] }))}
            onChange={(value) => setRole(value as Role)}
          />
          <TextField
            id="team-invite-email"
            label="Email"
            type="email"
            inputMode="email"
            autoComplete="off"
            maxLength={254}
            hint="We email the invitation. It works once and expires in 7 days."
            value={email}
            error={problems["email"] ?? (missingContact ? NEEDS_CONTACT : undefined)}
            onChange={setEmail}
          />
          <TextField
            id="team-invite-phone"
            label="Phone"
            type="tel"
            inputMode="tel"
            autoComplete="off"
            maxLength={20}
            hint="A 10-digit Indian number is fine. With no email, you get a link to share."
            value={phone}
            error={problems["phone"]}
            onChange={setPhone}
          />
          <Button type="submit" variant="primary" disabled={submitting}>
            {submitting ? "Sending…" : "Send invitation"}
          </Button>
        </form>
      </div>
    </Drawer>
  );
}
