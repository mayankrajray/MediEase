/**
 * M7e, A11 (ARCHITECTURE §9 "Client address"): the browser's address, passed to the API.
 *
 * Every browser request reaches the API through this server, so the API sees this server's
 * address. src/proxy.ts runs on every request (pages and /api) and:
 * 1. removes any `x-mediease-client-ip` / `x-mediease-proxy-secret` the browser sent, always;
 * 2. when `TRUSTED_PROXY_SECRET` and `CLIENT_IP_HEADER` are set, adds the browser's address,
 *    read from the header that the hosting edge in front of this server writes, with the secret.
 * The API trusts the address only with that secret (delivery/http/request_info.py). With either
 * setting empty (local compose, CI), nothing is added and the API uses the connection's address.
 *
 * `CLIENT_IP_HEADER` names the edge's header, e.g. `x-real-ip` on Vercel or `x-forwarded-for`
 * behind Caddy or nginx. The last value is taken: an edge appends the address it saw, so anything
 * before it may have been written by the browser.
 */

export const CLIENT_IP_HEADER = "x-mediease-client-ip";
export const PROXY_SECRET_HEADER = "x-mediease-proxy-secret";

export interface ForwardingConfig {
  readonly secret: string;
  readonly sourceHeader: string;
}

export function forwardingConfig(env: Readonly<Record<string, string | undefined>> = process.env): ForwardingConfig {
  return { secret: env.TRUSTED_PROXY_SECRET?.trim() ?? "", sourceHeader: env.CLIENT_IP_HEADER?.trim().toLowerCase() ?? "" };
}

// Digits, hex, dots and colons only, so nothing else ever travels in the header; the API parses it.
const ADDRESS = /^[0-9A-Fa-f.:]{2,45}$/;

/** The address the edge wrote: the last comma-separated value of its header, if it looks like one. */
export function edgeAddress(headers: Headers, sourceHeader: string): string | undefined {
  if (sourceHeader === "") return undefined;
  const last = headers.get(sourceHeader)?.split(",").pop()?.trim();
  return last !== undefined && ADDRESS.test(last) ? last : undefined;
}

/** The request's headers without anything the browser may not set, plus the address when configured. */
export function withClientAddress(incoming: Headers, config: ForwardingConfig): Headers {
  const headers = new Headers(incoming);
  headers.delete(CLIENT_IP_HEADER);
  headers.delete(PROXY_SECRET_HEADER);
  if (config.secret === "") return headers;
  const address = edgeAddress(incoming, config.sourceHeader);
  if (address === undefined) return headers;
  headers.set(CLIENT_IP_HEADER, address);
  headers.set(PROXY_SECRET_HEADER, config.secret);
  return headers;
}

/** For a server-side call to the API: the two headers the proxy put on this request, if any. */
export function forwardedFrom(headers: Pick<Headers, "get">): Record<string, string> {
  const address = headers.get(CLIENT_IP_HEADER);
  const secret = headers.get(PROXY_SECRET_HEADER);
  return address !== null && secret !== null ? { [CLIENT_IP_HEADER]: address, [PROXY_SECRET_HEADER]: secret } : {};
}
