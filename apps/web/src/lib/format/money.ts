/** Money for people (M5-P6): the API sends whole paise; shown as rupees with two decimals. */

const RUPEES = new Intl.NumberFormat("en-IN", {
  style: "currency",
  currency: "INR",
  minimumFractionDigits: 2,
  maximumFractionDigits: 2,
});

/** 12 → "₹0.12", 123456 → "₹1,234.56". */
export function formatPaise(paise: number): string {
  return RUPEES.format(paise / 100);
}

/** M6c-P5 fees: the rupee figure without the sign, and without decimals when whole (30000 → "300"). */
export function rupees(paise: number): string {
  return paise % 100 === 0 ? String(paise / 100) : (paise / 100).toFixed(2);
}

/** M6d (B1): the most one price or bill line may be, in paise (₹1,00,000). */
export const MAX_PRICE_PAISE = 10_000_000;

export type ParsedRupees = { readonly ok: true; readonly paise: number | null } | { readonly ok: false };

/**
 * M6d-P1: rupees typed by a person to paise. Empty is "no price"; "500", "500.5" and "1,500.25"
 * are fine; more than two decimals, a sign or more than ₹1,00,000 is refused.
 */
export function parseRupees(text: string): ParsedRupees {
  const cleaned = text.trim().replaceAll(",", "");
  if (cleaned === "") return { ok: true, paise: null };
  const match = /^(\d{1,7})(?:\.(\d{1,2}))?$/.exec(cleaned);
  if (match === null) return { ok: false };
  const paise = Number(match[1]) * 100 + Number((match[2] ?? "").padEnd(2, "0"));
  return paise > MAX_PRICE_PAISE ? { ok: false } : { ok: true, paise };
}

/** M6d-P1: paise as an editable rupee figure ("500", "500.50"), empty for no price. */
export function rupeesInput(paise: number | null): string {
  return paise === null ? "" : rupees(paise);
}
