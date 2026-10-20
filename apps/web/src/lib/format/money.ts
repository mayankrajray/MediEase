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
