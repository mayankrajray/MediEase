/**
 * The draft editor's rows and their conversion to the API's lines (M6d-P2; billing R15-R17).
 * People type rupees and percents; the API takes paise and hundredths of a percent. Nothing is
 * summed here: the API answers the totals.
 */

import { parseRupees, rupeesInput } from "@/lib/format/money";

import type { Bill, BillLineInput, Discount, DiscountKind } from "./api";

export interface DiscountRow {
  readonly kind: DiscountKind;
  /** Rupees for AMOUNT, a percent for PERCENT, empty for NONE. */
  readonly value: string;
}

export interface LineRow {
  readonly key: string;
  readonly serviceId: string;
  readonly description: string;
  readonly price: string;
  readonly quantity: string;
  readonly discount: DiscountRow;
}

export const NO_DISCOUNT_ROW: DiscountRow = { kind: "NONE", value: "" };

let keys = 0;
export const newKey = () => `line-${(keys += 1)}`;

export function emptyRow(): LineRow {
  return { key: newKey(), serviceId: "", description: "", price: "", quantity: "1", discount: NO_DISCOUNT_ROW };
}

/** "12.5" -> 1250 (hundredths of a percent); null when it is not 0-100 with two decimals. */
export function parsePercent(text: string): number | null {
  const match = /^(\d{1,3})(?:\.(\d{1,2}))?$/.exec(text.trim());
  if (match === null) return null;
  const value = Number(match[1]) * 100 + Number((match[2] ?? "").padEnd(2, "0"));
  return value <= 10_000 ? value : null;
}

export function percentInput(hundredths: number): string {
  return hundredths % 100 === 0 ? String(hundredths / 100) : (hundredths / 100).toFixed(2).replace(/0$/, "");
}

export function discountRow(discount: Discount): DiscountRow {
  if (discount.kind === "AMOUNT") return { kind: "AMOUNT", value: rupeesInput(discount.value) };
  if (discount.kind === "PERCENT") return { kind: "PERCENT", value: percentInput(discount.value) };
  return NO_DISCOUNT_ROW;
}

/** The discount to send, or an error message for the field. */
export function toDiscount(row: DiscountRow): Discount | string {
  if (row.kind === "NONE") return { kind: "NONE", value: 0 };
  if (row.kind === "PERCENT") {
    const value = parsePercent(row.value);
    return value === null ? "Enter a percent from 0 to 100." : { kind: "PERCENT", value };
  }
  const parsed = parseRupees(row.value);
  return !parsed.ok || parsed.paise === null ? "Enter the discount in rupees." : { kind: "AMOUNT", value: parsed.paise };
}

export function rowsOf(bill: Bill): LineRow[] {
  return bill.lines.map((line) => ({
    key: newKey(),
    serviceId: line.service_id ?? "",
    description: line.description,
    price: rupeesInput(line.unit_price_paise),
    quantity: String(line.quantity),
    discount: discountRow(line.discount),
  }));
}

export type RowErrors = Partial<Record<"description" | "price" | "quantity" | "discount", string>>;

/** The API line for a row, or what is wrong with it. A row with a service may leave the price
 * empty: the API takes the doctor's price from the fee schedule. */
export function toLine(row: LineRow): { line: BillLineInput } | { errors: RowErrors } {
  const errors: RowErrors = {};
  const price = parseRupees(row.price);
  if (!price.ok) errors.price = "Enter rupees up to 1,00,000, with at most two decimals.";
  else if (price.paise === null && row.serviceId === "") errors.price = "Enter a price.";
  const description = row.description.trim();
  if (description === "" && row.serviceId === "") errors.description = "Enter what the line is for.";
  if (description.length > 80) errors.description = "At most 80 characters.";
  const quantity = /^\d{1,2}$/.test(row.quantity.trim()) ? Number(row.quantity) : 0;
  if (quantity < 1 || quantity > 99) errors.quantity = "1 to 99.";
  const discount = toDiscount(row.discount);
  if (typeof discount === "string") errors.discount = discount;
  if (Object.keys(errors).length > 0 || typeof discount === "string" || !price.ok) return { errors };
  return {
    line: {
      ...(row.serviceId === "" ? {} : { service_id: row.serviceId }),
      ...(description === "" ? {} : { description }),
      ...(price.paise === null ? {} : { unit_price_paise: price.paise }),
      quantity,
      discount,
    },
  };
}
