import { redirect } from "next/navigation";

/**
 * Until the clinic dashboard exists (M1, whose landing page is today's queue),
 * the only page is the system status page.
 */
export default function Home(): never {
  redirect("/status");
}
