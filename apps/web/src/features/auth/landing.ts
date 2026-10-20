/**
 * Where a signed-in person belongs, decided in one place (M1-P6 design,
 * "Landing"). The sign-in form, the invitation form, the session guard and the
 * clinic chooser all call this, so they can never disagree.
 *
 * Pure functions: no browser APIs, no network. The API stays the authority;
 * this only picks a screen (apps/web/CLAUDE.md "No business rules in the UI").
 */

import type { components } from "@/lib/api/schema";

export type Identity = components["schemas"]["Identity"];
export type Membership = components["schemas"]["Membership"];
export type SessionUser = components["schemas"]["SessionUser"];
export type Role = components["schemas"]["Role"];
export type ClinicStatus = components["schemas"]["ClinicStatus"];

/** What `POST /auth/sign-in` and `GET /me` both tell us about the person. */
export type PersonAccess = Pick<Identity, "user" | "memberships">;

/** M6-P1 (decision 6A): where every clinic member lands. The queue keeps its own URL. */
export const TODAY_PATH = "/today";
export const OPS_PATH = "/ops";
export const SELECT_CLINIC_PATH = "/select-clinic";

export type ClinicChoice =
  /** No active membership: there is no clinic to work in. */
  | { readonly kind: "none" }
  /** Exactly one clinic is in play. `sendClinicHeader` is false for single-membership users (R6). */
  | { readonly kind: "active"; readonly membership: Membership; readonly sendClinicHeader: boolean }
  /** Several clinics and no usable preference: the person must pick. */
  | { readonly kind: "choose" };

/**
 * Picks the working clinic. `preferredId` is a preference only (a remembered or
 * just-chosen ID); one that is not among the memberships is ignored.
 */
export function chooseClinic(
  memberships: readonly Membership[],
  preferredId: string | null,
): ClinicChoice {
  const [only, ...others] = memberships;
  if (only === undefined) {
    return { kind: "none" };
  }
  if (others.length === 0) {
    return { kind: "active", membership: only, sendClinicHeader: false };
  }
  const preferred = memberships.find((m) => m.clinic_id === preferredId);
  return preferred === undefined
    ? { kind: "choose" }
    : { kind: "active", membership: preferred, sendClinicHeader: true };
}

export type Landing =
  | { readonly kind: "ops" }
  | { readonly kind: "none" }
  | { readonly kind: "choose" }
  | { readonly kind: "active"; readonly membership: Membership; readonly sendClinicHeader: boolean };

/** Ops users work in the ops console only (spec R10), whatever memberships they hold. */
export function resolveLanding(person: PersonAccess, preferredClinicId: string | null): Landing {
  if (person.user.is_platform_ops) {
    return { kind: "ops" };
  }
  return chooseClinic(person.memberships, preferredClinicId);
}

/** Only the ops console is open to ops users; `next` is honoured inside it. */
function insideOps(path: string): boolean {
  return path === OPS_PATH || path.startsWith(`${OPS_PATH}/`) || path.startsWith(`${OPS_PATH}?`);
}

/**
 * The path to open right after signing in. `next` must already have passed
 * `safeNextPath`; it is where the person was headed before being asked to sign in.
 */
export function postSignInPath(
  person: PersonAccess,
  preferredClinicId: string | null,
  next: string,
): string {
  const landing = resolveLanding(person, preferredClinicId);
  switch (landing.kind) {
    case "ops":
      return insideOps(next) ? next : OPS_PATH;
    case "choose":
      return next === TODAY_PATH
        ? SELECT_CLINIC_PATH
        : `${SELECT_CLINIC_PATH}?next=${encodeURIComponent(next)}`;
    case "none":
    case "active":
      return insideOps(next) ? TODAY_PATH : next;
  }
}
