import { describe, expect, it } from "vitest";

import { noShowRate, placeLabel, sessionHours } from "./labels";

describe("Today's words (M6-P1)", () => {
  it("names a place by token, else by the slot's time on the clinic's clock", () => {
    expect(placeLabel({ token_number: 7, slot_start: null }, "Asia/Kolkata")).toBe("Token 7");
    expect(placeLabel({ token_number: null, slot_start: "2026-10-20T05:00:00+00:00" }, "Asia/Kolkata")).toBe("10:30");
    expect(placeLabel({ token_number: null, slot_start: null }, "Asia/Kolkata")).toBe("–");
  });

  it("gives the no-show rate as a whole percentage, and a dash for a day with no appointments", () => {
    expect(noShowRate({ appointments: 8, no_show: 2 })).toBe("25%");
    expect(noShowRate({ appointments: 3, no_show: 1 })).toBe("33%");
    expect(noShowRate({ appointments: 0, no_show: 0 })).toBe("–");
  });

  it("shows a session's hours in the clinic's zone", () => {
    expect(
      sessionHours({ starts_at: "2026-10-20T04:30:00+00:00", ends_at: "2026-10-20T07:30:00+00:00" }, "Asia/Kolkata"),
    ).toBe("10:00–13:00");
  });
});
