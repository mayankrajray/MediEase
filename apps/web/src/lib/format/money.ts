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
