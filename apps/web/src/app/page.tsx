import { redirect } from "next/navigation";

import { QUEUE_PATH } from "@/features/auth/landing";

/**
 * The home page is the clinic queue. Signed-out visitors are sent to /sign-in by
 * the proxy, and anyone the proxy lets through is checked by the session provider.
 */
export default function Home(): never {
  redirect(QUEUE_PATH);
}
