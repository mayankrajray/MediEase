"use client";

import { useEffect, useState } from "react";

import { Button } from "@/components/ui/Button";
import { EmptyState } from "@/components/ui/EmptyState";
import { LIST_ITEM, LayoutMotion } from "@/components/ui/LayoutMotion";
import { m } from "@/components/ui/Motion";
import { PageHeader } from "@/components/ui/PageHeader";
import { Skeleton } from "@/components/ui/Skeleton";
import { StatusBadge } from "@/components/ui/StatusBadge";
import { TABLE, TABLE_WRAP, TD, TH, TR } from "@/components/ui/table";
import { ErrorNotice } from "@/features/auth/ErrorNotice";
import { ROLE_LABELS } from "@/features/auth/labels";
import { TODAY_PATH } from "@/features/auth/landing";
import { useSession } from "@/features/auth/SessionProvider";
import { useClinic } from "@/features/shell/ClinicGate";
import { formatDateTime } from "@/lib/format/time";

import { useTeamApi, type StaffMember, type TeamInvitation } from "./api";
import { InviteDrawer } from "./InviteDrawer";
import { ChangeRoleDialog, DeactivateDialog, LinkDialog, LinkDoctorDialog } from "./MemberDialogs";
import { STATUS_LABELS, STATUS_TONES, contactOf, sortTeam } from "./labels";

type Load =
  | { readonly status: "loading" }
  | { readonly status: "ready"; readonly members: readonly StaffMember[] }
  | { readonly status: "failed"; readonly error: unknown };

type Open =
  | { readonly kind: "invite"; readonly again?: StaffMember }
  | { readonly kind: "role"; readonly member: StaffMember }
  | { readonly kind: "deactivate"; readonly member: StaffMember }
  | { readonly kind: "link-doctor"; readonly member: StaffMember }
  | { readonly kind: "link"; readonly invitation: TeamInvitation };

/** After demoting yourself, or linking your own doctor profile, the session is stale: reload. */
function leaveForToday(): void {
  window.location.assign(TODAY_PATH);
}

/**
 * The owner's Team page (M6a-P5, FR-ORG-07): everyone in the clinic with their role and status;
 * invite, resend, change a role, deactivate and invite back. Owners only (`STAFF_MANAGE`); the
 * API refuses everyone else. Every change updates its row in place and says so in a status line.
 */
export function TeamPage({
  onSelfDemoted = leaveForToday,
  initialInvite = false,
}: { onSelfDemoted?: () => void; initialInvite?: boolean } = {}) {
  const api = useTeamApi();
  const clinic = useClinic();
  const { clinic: choice, endSession } = useSession();
  const myMembership = choice.kind === "active" ? choice.membership.membership_id : undefined;
  const [load, setLoad] = useState<Load>({ status: "loading" });
  const [attempt, setAttempt] = useState(0);
  const [open, setOpen] = useState<Open | undefined>(initialInvite ? { kind: "invite" } : undefined);
  const [message, setMessage] = useState("");
  const [rowError, setRowError] = useState<unknown>(null);
  const [resending, setResending] = useState<string | undefined>(undefined);

  useEffect(() => {
    let cancelled = false;
    api.list().then(
      (members) => {
        if (!cancelled) setLoad({ status: "ready", members });
      },
      (failure: unknown) => {
        if (!cancelled && !endSession(failure)) setLoad({ status: "failed", error: failure });
      },
    );
    return () => {
      cancelled = true;
    };
  }, [api, attempt, endSession]);

  function put(member: StaffMember) {
    setLoad((current) =>
      current.status !== "ready"
        ? current
        : {
            status: "ready",
            members: current.members.some((m) => m.membership_id === member.membership_id)
              ? current.members.map((m) => (m.membership_id === member.membership_id ? member : m))
              : [...current.members, member],
          },
    );
  }

  function invited(invitation: TeamInvitation) {
    put(invitation);
    setRowError(null);
    setMessage(
      invitation.delivery === "email"
        ? `Invitation emailed to ${invitation.email_masked ?? "them"}.`
        : `Invitation created for ${invitation.full_name}. Share the link with them.`,
    );
  }

  async function resend(member: StaffMember) {
    if (resending !== undefined) return;
    setResending(member.membership_id);
    setRowError(null);
    try {
      const invitation = await api.resend(member.membership_id);
      invited(invitation);
      if (invitation.accept_url !== null) setOpen({ kind: "link", invitation });
    } catch (failure) {
      if (!endSession(failure)) setRowError(failure);
    } finally {
      setResending(undefined);
    }
  }

  return (
    <section className="space-y-4">
      <PageHeader
        title="Team"
        description="Everyone who works in this clinic, their role and whether they can sign in."
        actions={
          <Button variant="primary" onClick={() => setOpen({ kind: "invite" })}>
            Invite someone
          </Button>
        }
      />
      <p role="status" className="min-h-6 font-medium text-emerald-900">
        {message}
      </p>
      {rowError !== null && (
        <div className="max-w-xl">
          <ErrorNotice error={rowError} />
        </div>
      )}

      {load.status === "loading" && (
        <div className="space-y-2">
          <p role="status" className="sr-only">
            Loading the team…
          </p>
          <Skeleton className="h-12 w-full" />
          <Skeleton className="h-12 w-full" />
          <Skeleton className="h-12 w-full" />
        </div>
      )}
      {load.status === "failed" && (
        <div className="max-w-xl">
          <ErrorNotice
            error={load.error}
            onRetry={() => {
              setLoad({ status: "loading" });
              setAttempt((n) => n + 1);
            }}
          />
        </div>
      )}
      {load.status === "ready" && load.members.length === 0 && <EmptyState title="Nobody is in this team yet." />}
      {load.status === "ready" && load.members.length > 0 && (
        <LayoutMotion>
          <div className={TABLE_WRAP}>
            <table role="table" className={TABLE}>
              <caption className="sr-only">Team members: active first, then invited, then deactivated</caption>
              <thead role="rowgroup">
                <tr role="row">
                  <th role="columnheader" scope="col" className={TH}>Name</th>
                  <th role="columnheader" scope="col" className={TH}>Role</th>
                  <th role="columnheader" scope="col" className={TH}>Status</th>
                  <th role="columnheader" scope="col" className={TH}>Email or phone</th>
                  <th role="columnheader" scope="col" className={TH}>
                    <span className="sr-only">Actions</span>
                  </th>
                </tr>
              </thead>
              <tbody role="rowgroup">
                {sortTeam(load.members).map((member) => {
                  const isYou = member.membership_id === myMembership;
                  return (
                    <m.tr {...LIST_ITEM} role="row" key={member.membership_id} className={TR}>
                      <th role="rowheader" scope="row" className={`${TD} font-medium`}>
                        {member.full_name}
                        {isYou && <span className="font-normal text-slate-700"> (you)</span>}
                      </th>
                      <td role="cell" data-label="Role" className={TD}>
                        {ROLE_LABELS[member.role]}
                        {member.has_doctor_profile && (
                          <span className="ml-2 inline-block rounded bg-brand-50 px-1.5 py-0.5 text-sm text-brand-900">
                            Doctor profile
                          </span>
                        )}
                      </td>
                      <td role="cell" data-label="Status" className={TD}>
                        <StatusBadge tone={STATUS_TONES[member.status]}>{STATUS_LABELS[member.status]}</StatusBadge>
                        {member.status === "INVITED" && (
                          <span className="block text-sm text-slate-700">
                            {member.invite_expires_at === null
                              ? "Sending the email…"
                              : `Link expires ${formatDateTime(member.invite_expires_at, clinic.timezone)}`}
                          </span>
                        )}
                      </td>
                      <td role="cell" data-label="Email or phone" className={`${TD} break-all`}>
                        {contactOf(member)}
                      </td>
                      <td role="cell" data-label="" className={TD}>
                        <div className="flex flex-wrap gap-2">
                          {member.status === "INVITED" && (
                            <Button
                              size="sm"
                              disabled={resending !== undefined}
                              onClick={() => void resend(member)}
                            >
                              {resending === member.membership_id ? "Resending…" : "Resend"}{" "}
                              <span className="sr-only">invitation to {member.full_name}</span>
                            </Button>
                          )}
                          {member.status !== "DEACTIVATED" && (
                            <Button size="sm" onClick={() => setOpen({ kind: "role", member })}>
                              Change role{" "}<span className="sr-only">of {member.full_name}</span>
                            </Button>
                          )}
                          {member.status === "ACTIVE" &&
                            !member.has_doctor_profile &&
                            (member.role === "OWNER" || member.role === "DOCTOR") && (
                              <Button size="sm" onClick={() => setOpen({ kind: "link-doctor", member })}>
                                Link doctor profile{" "}<span className="sr-only">to {member.full_name}</span>
                              </Button>
                            )}
                          {member.status !== "DEACTIVATED" && !isYou && (
                            <Button size="sm" variant="ghost" onClick={() => setOpen({ kind: "deactivate", member })}>
                              Deactivate{" "}<span className="sr-only">{member.full_name}</span>
                            </Button>
                          )}
                          {member.status === "DEACTIVATED" && (
                            <Button size="sm" onClick={() => setOpen({ kind: "invite", again: member })}>
                              Invite back{" "}<span className="sr-only">{member.full_name}</span>
                            </Button>
                          )}
                        </div>
                      </td>
                    </m.tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </LayoutMotion>
      )}

      {open?.kind === "invite" && (
        <InviteDrawer
          {...(open.again === undefined ? {} : { again: open.again })}
          onInvited={invited}
          onClose={() => setOpen(undefined)}
        />
      )}
      {open?.kind === "role" && (
        <ChangeRoleDialog
          member={open.member}
          isYou={open.member.membership_id === myMembership}
          onChanged={(member) => {
            setOpen(undefined);
            if (member.membership_id === myMembership && member.role !== "OWNER") {
              onSelfDemoted();
              return;
            }
            put(member);
            setMessage(`${member.full_name} is now ${ROLE_LABELS[member.role]}.`);
          }}
          onClose={() => setOpen(undefined)}
        />
      )}
      {open?.kind === "deactivate" && (
        <DeactivateDialog
          member={open.member}
          onDeactivated={(member) => {
            setOpen(undefined);
            put(member);
            setMessage(`${member.full_name} is deactivated.`);
          }}
          onClose={() => setOpen(undefined)}
        />
      )}
      {open?.kind === "link-doctor" && (
        <LinkDoctorDialog
          member={open.member}
          isYou={open.member.membership_id === myMembership}
          onLinked={(member) => {
            setOpen(undefined);
            if (member.membership_id === myMembership) {
              // Your permissions and workspaces changed: reload them from Today.
              onSelfDemoted();
              return;
            }
            put(member);
            setMessage(`${member.full_name} is linked to a doctor profile.`);
          }}
          onClose={() => setOpen(undefined)}
        />
      )}
      {open?.kind === "link" && <LinkDialog invitation={open.invitation} onClose={() => setOpen(undefined)} />}
    </section>
  );
}
