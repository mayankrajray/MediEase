/**
 * Phone numbers on screen (apps/web/CLAUDE.md: masked except where staff must dial them).
 * The mask matches the API's logs (CLAUDE.md "Observability": `+91******3210`).
 */

/** "+919000000101" -> "+91******0101". Anything too short to mask safely is fully hidden. */
export function maskPhone(e164: string): string {
  const digits = e164.startsWith("+") ? e164.slice(1) : e164;
  if (!/^\d{8,15}$/.test(digits)) {
    return "••••";
  }
  const country = digits.startsWith("91") ? "91" : digits.slice(0, 1);
  const last = digits.slice(-4);
  const hidden = digits.length - country.length - last.length;
  return `+${country}${"*".repeat(hidden)}${last}`;
}

/** "+919000000101" -> "+91 90000 00101" for an Indian mobile, so it can be read aloud; others as given. */
export function formatPhone(e164: string): string {
  const match = /^\+91(\d{5})(\d{5})$/.exec(e164);
  return match === null ? e164 : `+91 ${match[1]} ${match[2]}`;
}
