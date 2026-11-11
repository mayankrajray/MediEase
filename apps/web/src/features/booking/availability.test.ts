import { describe, expect, it } from "vitest";

import {
  addDays,
  choiceOf,
  clinicToday,
  findOffer,
  groupByPart,
  inWindow,
  isStale,
  lastDate,
  nextAvailableAfter,
  offersOn,
  partOfDay,
  placesOn,
  stripDates,
  type Days,
} from "./availability";

const TZ = "Asia/Kolkata";

// Thu 12 Nov 2026 (IST): a slot session in the morning, a token session in the afternoon and
// one in the evening. Sat 14 Nov: one token session. Fri 13 Nov is left out (nothing free).
const DAYS: Days = [
  {
    date: "2026-11-12",
    sessions: [
      {
        starts_at: "2026-11-12T03:30:00Z", // 09:00
        ends_at: "2026-11-12T05:30:00Z",
        mode: "SLOTS",
        places_left: 4,
        slots: ["03:30", "04:00", "04:30", "05:00"].map((t) => ({ starts_at: `2026-11-12T${t}:00Z`, ends_at: `2026-11-12T${t}:00Z` })),
      },
      { starts_at: "2026-11-12T11:30:00Z", ends_at: "2026-11-12T13:30:00Z", mode: "TOKENS", places_left: 2, slots: [] }, // 17:00 evening
      { starts_at: "2026-11-12T08:30:00Z", ends_at: "2026-11-12T10:30:00Z", mode: "TOKENS", places_left: 12, slots: [] }, // 14:00 afternoon
    ],
  },
  { date: "2026-11-14", sessions: [{ starts_at: "2026-11-14T03:30:00Z", ends_at: "2026-11-14T07:30:00Z", mode: "TOKENS", places_left: 1, slots: [] }] },
];

describe("booking dates (M7d-P2, design §7)", () => {
  it("counts the window from the clinic's date: today and the next 13 days, never a past date", () => {
    // 20:00 UTC on 11 Nov is already 12 Nov in India.
    expect(clinicToday(new Date("2026-11-11T20:00:00Z"), TZ)).toBe("2026-11-12");
    expect(clinicToday(new Date("2026-11-11T20:00:00Z"), "UTC")).toBe("2026-11-11");
    expect(lastDate("2026-11-12")).toBe("2026-11-25");
    expect(inWindow("2026-11-12", "2026-11-12")).toBe(true);
    expect(inWindow("2026-11-25", "2026-11-12")).toBe(true);
    expect(inWindow("2026-11-26", "2026-11-12")).toBe(false);
    expect(inWindow("2026-11-11", "2026-11-12")).toBe(false);
    expect(inWindow("2026-02-30", "2026-02-01")).toBe(false); // not a real date
    expect(inWindow("2026-02-14", "2026-02-01")).toBe(true);
    expect(inWindow("not-a-date", "2026-11-12")).toBe(false);
  });

  it("shows today first and the next three dates, across a month end", () => {
    expect(stripDates("2026-11-29")).toEqual(["2026-11-29", "2026-11-30", "2026-12-01", "2026-12-02"]);
    expect(addDays("2026-12-31", 1)).toBe("2027-01-01");
  });

  it("finds the next date with something free, after the chosen one", () => {
    expect(nextAvailableAfter(DAYS, "2026-11-12")).toBe("2026-11-14");
    expect(nextAvailableAfter(DAYS, "2026-11-13")).toBe("2026-11-14");
    expect(nextAvailableAfter(DAYS, "2026-11-14")).toBeUndefined();
    expect(placesOn(DAYS, "2026-11-12")).toBe(18);
    expect(placesOn(DAYS, "2026-11-13")).toBe(0);
  });
});

describe("times of one date", () => {
  it("lists slots one by one and token sessions whole, in time order, by part of the clinic's day", () => {
    const offers = offersOn(DAYS, "2026-11-12", TZ);
    expect(offers.map((o) => o.part)).toEqual(["morning", "morning", "morning", "morning", "afternoon", "evening"]);
    expect(offers[4]?.slot).toBeNull();
    expect(groupByPart(offers).map((g) => [g.part, g.offers.length])).toEqual([
      ["morning", 4],
      ["afternoon", 1],
      ["evening", 1],
    ]);
    expect(offersOn(DAYS, "2026-11-13", TZ)).toEqual([]);
  });

  it("splits the day at 12:00 and 17:00 on the clinic's clock, not the browser's", () => {
    expect(partOfDay("2026-11-12T06:29:00Z", TZ)).toBe("morning"); // 11:59
    expect(partOfDay("2026-11-12T06:30:00Z", TZ)).toBe("afternoon"); // 12:00
    expect(partOfDay("2026-11-12T11:29:00Z", TZ)).toBe("afternoon"); // 16:59
    expect(partOfDay("2026-11-12T11:30:00Z", TZ)).toBe("evening"); // 17:00
    expect(partOfDay("2026-11-12T06:30:00Z", "UTC")).toBe("morning");
  });

  it("keeps a choice only while the latest answer still offers it (stale-data guard)", () => {
    const slot = offersOn(DAYS, "2026-11-12", TZ)[1];
    expect(slot).toBeDefined();
    const choice = choiceOf(slot!);
    expect(choice).toEqual({ session: "2026-11-12T03:30:00Z", slot: "2026-11-12T04:00:00Z" });
    expect(findOffer(DAYS, "2026-11-12", choice, TZ)?.key).toBe(slot?.key);
    const taken: Days = [{ ...DAYS[0]!, sessions: DAYS[0]!.sessions.map((s) => (s.mode === "SLOTS" ? { ...s, places_left: 3, slots: s.slots.filter((x) => x.starts_at !== choice.slot) } : s)) }];
    expect(findOffer(taken, "2026-11-12", choice, TZ)).toBeUndefined();
    const full: Days = [{ ...DAYS[0]!, sessions: DAYS[0]!.sessions.map((s) => ({ ...s, places_left: 0 })) }];
    expect(offersOn(full, "2026-11-12", TZ)).toEqual([]);
    expect(findOffer(DAYS, "2026-11-12", null, TZ)).toBeUndefined();
  });

  it("calls an answer stale after a minute", () => {
    expect(isStale(0, 59_999)).toBe(false);
    expect(isStale(0, 60_000)).toBe(true);
  });
});
