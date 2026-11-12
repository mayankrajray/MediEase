import { headers } from "next/headers";

/** The nonce of this response's CSP (src/proxy.ts sets the policy on the request as well). */
export function nonceFrom(csp: string | null): string | undefined {
  return csp?.match(/'nonce-([^']+)'/)?.[1];
}

/**
 * M7e-E1 (design §7 Q2, fallback B): a plain async `<script>` for `public/sw-register.js` with this
 * response's nonce, about 1.5 KB and no React. Rendered by the staff and portal layouts only: the
 * landing page, search, clinic pages and the token pages have no room in their 200 KB budget, and
 * one registration covers the whole site (scope `/`), so they still get the offline page once
 * the app has been opened anywhere.
 */
export async function RegisterServiceWorker() {
  const nonce = nonceFrom((await headers()).get("Content-Security-Policy"));
  return <script src="/sw-register.js" async nonce={nonce} />;
}
