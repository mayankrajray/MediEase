/**
 * Reading the local stack's email (M6a-P4, ADR-0016 decision 3): the worker sends into Mailpit,
 * whose API the journeys poll for a message to one address.
 */

import { expect, type APIRequestContext } from "@playwright/test";

const MAILPIT = process.env.E2E_MAILPIT_URL ?? "http://mailpit:8025";

interface Summary {
  readonly ID: string;
  readonly Subject: string;
}

/** The text body of the newest email to `to` whose subject contains `subject`. */
export async function waitForEmail(request: APIRequestContext, to: string, subject: string): Promise<string> {
  let id: string | undefined;
  await expect
    .poll(
      async () => {
        const resp = await request.get(`${MAILPIT}/api/v1/search`, { params: { query: `to:"${to}"` } });
        const found = ((await resp.json()) as { messages: Summary[] }).messages.find((m) =>
          m.Subject.includes(subject),
        );
        id = found?.ID;
        return id !== undefined;
      },
      { timeout: 20_000, message: `an email "${subject}" to ${to}` },
    )
    .toBe(true);
  const message = await request.get(`${MAILPIT}/api/v1/message/${id ?? ""}`);
  return ((await message.json()) as { Text: string }).Text;
}

/** The path of the first link to `prefix` in an email (the host is PUBLIC_BASE_URL, not ours). */
export function linkPath(text: string, prefix: string): string {
  const match = text.match(new RegExp(`https?://[^\\s/]+(${prefix}/[A-Za-z0-9_-]+)`));
  expect(match, `a ${prefix} link`).not.toBeNull();
  return match?.[1] ?? "";
}
