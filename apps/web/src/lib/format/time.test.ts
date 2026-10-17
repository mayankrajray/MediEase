import { describe, expect, it } from "vitest";

import { addDays, formatClock, formatDateTime, formatDay, formatDuration, minutesBetween } from "./time";

describe("formatDateTime", () => {
  it("FR-OPS-04: shows the moment in the clinic's own zone, labelled", () => {
    // 08:35 UTC is 14:05 in India (+5:30) and 12:35 in Dubai (+4).
    expect(formatDateTime("2026-10-03T08:35:00+00:00", "Asia/Kolkata")).toMatch(/3 Oct 2026.*14:05.*IST/);
    expect(formatDateTime("2026-10-03T08:35:00+00:00", "Asia/Dubai")).toMatch(/12:35/);
  });

  it("does not depend on the machine's time zone", () => {
    const a = formatDateTime("2026-10-03T23:30:00+05:30", "Asia/Kolkata");
    expect(a).toMatch(/3 Oct 2026.*23:30/);
  });

  it("falls back to UTC for an unknown zone instead of throwing", () => {
    expect(formatDateTime("2026-10-03T08:35:00+00:00", "Mars/Olympus")).toMatch(/08:35.*UTC/);
  });

  it("shows a dash for an unreadable value", () => {
    expect(formatDateTime("not a date", "Asia/Kolkata")).toBe("–");
  });
});

describe("minutesBetween", () => {
  it("counts whole minutes", () => {
    expect(minutesBetween("2026-10-03T08:00:00+00:00", "2026-10-03T08:12:59+00:00")).toBe(12);
  });

  it("accepts a timestamp or a Date as the end", () => {
    const end = new Date("2026-10-03T09:00:00+00:00");
    expect(minutesBetween("2026-10-03T08:00:00+00:00", end)).toBe(60);
    expect(minutesBetween("2026-10-03T08:00:00+00:00", end.getTime())).toBe(60);
  });

  it("is never negative (clock skew between the API and the browser)", () => {
    expect(minutesBetween("2026-10-03T08:05:00+00:00", "2026-10-03T08:00:00+00:00")).toBe(0);
  });

  it("is undefined when a value is unreadable", () => {
    expect(minutesBetween("nope", "2026-10-03T08:00:00+00:00")).toBeUndefined();
  });
});

describe("formatDuration", () => {
  it.each([
    [0, "under 1 min"],
    [1, "1 min"],
    [59, "59 min"],
    [60, "1 h 00 min"],
    [65, "1 h 05 min"],
    [185, "3 h 05 min"],
  ])("%s minutes -> %s", (minutes, text) => {
    expect(formatDuration(minutes)).toBe(text);
  });
});

describe("formatClock, formatDay, addDays (M3-P5)", () => {
  it("AC5: shows a session's times on the clinic's clock at both midnight edges", () => {
    expect(formatClock("2026-10-19T04:30:00+00:00", "Asia/Kolkata")).toBe("10:00");
    // 18:30 UTC is midnight in Kolkata; 18:29 is still 23:59 the day before.
    expect(formatClock("2026-10-19T18:30:00+00:00", "Asia/Kolkata")).toBe("00:00");
    expect(formatClock("2026-10-19T18:29:00+00:00", "Asia/Kolkata")).toBe("23:59");
    expect(formatClock("not a time", "Asia/Kolkata")).toBe("–");
    expect(formatClock("2026-10-19T04:30:00+00:00", "Not/AZone")).toBe("04:30");
  });

  it("names a calendar date and steps across months", () => {
    expect(formatDay("2026-10-19")).toBe("Mon, 19 Oct");
    expect(addDays("2026-10-31", 1)).toBe("2026-11-01");
    expect(addDays("2026-11-01", -1)).toBe("2026-10-31");
  });
});
