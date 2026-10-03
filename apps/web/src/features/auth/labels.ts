import type { Role } from "./landing";

/** Staff-facing names for roles (English at MVP, NFR-11). */
export const ROLE_LABELS: Readonly<Record<Role, string>> = {
  OWNER: "Owner",
  DOCTOR: "Doctor",
  FRONT_DESK: "Front desk",
};
