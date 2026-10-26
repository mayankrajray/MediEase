import { describe, expect, it } from "vitest";

import { formatPaise, parseRupees, rupees, rupeesInput } from "./money";

describe("money (M5-P6, M6d-P1 B1)", () => {
  it("shows paise as rupees", () => {
    expect(formatPaise(123456)).toBe("₹1,234.56");
    expect(rupees(30000)).toBe("300");
    expect(rupees(30050)).toBe("300.50");
  });

  it("reads typed rupees as paise", () => {
    expect(parseRupees("")).toEqual({ ok: true, paise: null });
    expect(parseRupees("  500 ")).toEqual({ ok: true, paise: 50000 });
    expect(parseRupees("500.5")).toEqual({ ok: true, paise: 50050 });
    expect(parseRupees("1,500.25")).toEqual({ ok: true, paise: 150025 });
    expect(parseRupees("0")).toEqual({ ok: true, paise: 0 });
    expect(parseRupees("100000")).toEqual({ ok: true, paise: 10_000_000 });
  });

  it("refuses what is not a price", () => {
    for (const text of ["100000.01", "-5", "5.123", "abc", "1e3", "."]) {
      expect(parseRupees(text)).toEqual({ ok: false });
    }
  });

  it("round-trips a price for editing", () => {
    expect(rupeesInput(null)).toBe("");
    expect(rupeesInput(50050)).toBe("500.50");
    expect(parseRupees(rupeesInput(50050))).toEqual({ ok: true, paise: 50050 });
  });
});
