/**
 * The last clinic a person worked in, remembered for new tabs and the next visit.
 *
 * It is a preference, not an authority (M1-P6 design, concept 5): the API
 * rejects a clinic the caller does not belong to, and `chooseClinic` ignores an
 * ID that is not one of the caller's memberships. Storage can be missing or
 * blocked (private mode, policy), so every access is guarded and a failure just
 * means "nothing remembered".
 */

export const CLINIC_STORAGE_KEY = "mediease.clinic_id";

const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i;

function storage(): Storage | undefined {
  try {
    return typeof window === "undefined" ? undefined : window.localStorage;
  } catch {
    return undefined;
  }
}

export function readRememberedClinic(): string | null {
  try {
    const value = storage()?.getItem(CLINIC_STORAGE_KEY) ?? null;
    return value !== null && UUID.test(value) ? value : null;
  } catch {
    return null;
  }
}

export function rememberClinic(clinicId: string): void {
  try {
    storage()?.setItem(CLINIC_STORAGE_KEY, clinicId);
  } catch {
    // Not remembering is harmless: the chooser simply appears again.
  }
}

export function forgetClinic(): void {
  try {
    storage()?.removeItem(CLINIC_STORAGE_KEY);
  } catch {
    // Nothing to forget, or storage is blocked.
  }
}
