import { describe, expect, it } from "vitest";

import { formatPhone, maskPhone } from "./phone";

describe("maskPhone", () => {
  it.each([
    ["+919000000101", "+91******0101"],
    ["+14155550123", "+1******0123"],
    ["+9190000", "••••"],
    ["not a phone", "••••"],
  ])("%s -> %s", (input, masked) => {
    expect(maskPhone(input)).toBe(masked);
  });

  it("never shows more than the country code and the last four digits", () => {
    expect(maskPhone("+919876543210")).not.toContain("98765");
  });
});

describe("formatPhone", () => {
  it("groups an Indian mobile for reading aloud and leaves other numbers alone", () => {
    expect(formatPhone("+919000000101")).toBe("+91 90000 00101");
    expect(formatPhone("+14155550123")).toBe("+14155550123");
  });
});
