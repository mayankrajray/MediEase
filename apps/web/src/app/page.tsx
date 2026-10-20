import { redirect } from "next/navigation";

import { TODAY_PATH } from "@/features/auth/landing";

/**
 * The home page is Today (M6-P1, decision 6A). Signed-out visitors are sent to /sign-in by the
 * proxy, and anyone the proxy lets through is checked by the session provider.
 */
export default function Home(): never {
  redirect(TODAY_PATH);
}
