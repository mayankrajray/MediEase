import { describe, expect, it } from "vitest";

import { discountRow, emptyRow, parsePercent, percentInput, toDiscount, toLine } from "./form";

describe("the bill editor's rows (M6d-P2, billing R15-R17)", () => {
  it("reads percents as hundredths", () => {
    expect(parsePercent("10")).toBe(1000);
    expect(parsePercent("12.5")).toBe(1250);
    expect(parsePercent("100")).toBe(10_000);
    expect(parsePercent("100.01")).toBeNull();
    expect(parsePercent("-1")).toBeNull();
    expect(percentInput(1250)).toBe("12.5");
    expect(percentInput(1000)).toBe("10");
    expect(discountRow({ kind: "PERCENT", value: 1250 })).toEqual({ kind: "PERCENT", value: "12.5" });
  });

  it("turns a row into the API's line in paise", () => {
    const row = { ...emptyRow(), description: " Dressing ", price: "150.50", quantity: "2", discount: { kind: "AMOUNT" as const, value: "50" } };
    expect(toLine(row)).toEqual({
      line: { description: "Dressing", unit_price_paise: 15050, quantity: 2, discount: { kind: "AMOUNT", value: 5000 } },
    });
    expect(toLine({ ...emptyRow(), serviceId: "svc" })).toEqual({ line: { service_id: "svc", quantity: 1, discount: { kind: "NONE", value: 0 } } });
  });

  it("says what is wrong with a row", () => {
    const result = toLine({ ...emptyRow(), price: "abc", quantity: "0", discount: { kind: "PERCENT", value: "200" } });
    expect(result).toEqual({
      errors: {
        price: "Enter rupees up to 1,00,000, with at most two decimals.",
        description: "Enter what the line is for.",
        quantity: "1 to 99.",
        discount: "Enter a percent from 0 to 100.",
      },
    });
    expect(toDiscount({ kind: "AMOUNT", value: "" })).toBe("Enter the discount in rupees.");
  });
});
