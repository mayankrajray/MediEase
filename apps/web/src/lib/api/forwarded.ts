import { headers } from "next/headers";

import { forwardedFrom } from "@/lib/security/client-address";

/**
 * M7e, A11: for a Server Component's call to the API, the browser's address as the proxy
 * vouched for it (src/lib/security/client-address.ts). Empty when forwarding is off. Server only:
 * `next/headers` cannot be imported by a client component, so a mistake fails the build.
 */
export async function forwardedClient(): Promise<Record<string, string>> {
  return forwardedFrom(await headers());
}
