import { readdirSync, readFileSync } from "node:fs";
import { join } from "node:path";

import { describe, expect, it } from "vitest";

import { vocabulary } from "@/features/visits/testing";
import { addDays } from "@/lib/format/time";

import { adviceInput, adviceText, daysBetween, draftBody, fromTemplate, isEmpty, moveLine, toLine, EMPTY_BODY } from "./draft";
import { frequencyLabel, frequencySlots, lineSummary, parseDuration, parseFrequency } from "./vocabulary";

describe("frequency shortcuts (spec §6; M6b-P3 prescriptions R21)", () => {
  it.each([
    ["101", "1-0-1"],
    ["1-0-1", "1-0-1"],
    ["1 0 1", "1-0-1"],
    ["110", "1-1-0"],
    ["010", "0-1-0"],
    ["1011", "1-0-1-1"],
    ["0-0-1-0", "0-0-1-0"],
    ["1111", "1-1-1-1"],
    ["s", "SOS"],
    ["SOS", "SOS"],
    ["o", "ONCE"],
    ["once", "ONCE"],
    ["C", "CUSTOM"],
  ])("%s reads as %s", (typed, code) => {
    expect(parseFrequency(typed, vocabulary)).toBe(code);
  });

  it.each(["", "  ", "000", "0-0-0-0", "1x", "202", "2-0-2", "½-0-½", "10", "10101", "daily"])("%j is not a code", (typed) => {
    expect(parseFrequency(typed, vocabulary)).toBeUndefined();
  });

  it("reads patterns only once the API's slot sets have loaded", () => {
    expect(parseFrequency("101", undefined)).toBeUndefined();
    expect(parseFrequency("s", undefined)).toBe("SOS");
  });

  it("labels say the code and the API's slots; a custom one is the doctor's words", () => {
    expect(frequencyLabel("1-0-1", null, vocabulary)).toBe("1-0-1 · morning and night");
    expect(frequencyLabel("1-1-0", null, vocabulary)).toBe("1-1-0 · morning and afternoon");
    expect(frequencyLabel("0-0-1-0", null, vocabulary)).toBe("0-0-1-0 · evening");
    expect(frequencyLabel("1-1-1-1", null, vocabulary)).toBe("1-1-1-1 · morning, afternoon, evening and night");
    expect(frequencyLabel("CUSTOM", "every other day", vocabulary)).toBe("every other day");
    expect(frequencySlots("1-0-1-1", vocabulary)).toEqual(["MORNING", "EVENING", "NIGHT"]);
  });

  it("D8: no source file keeps its own copy of the slot sets", () => {
    const dir = join(process.cwd(), "src", "features", "prescriptions");
    const sources = readdirSync(dir).filter((f) => /\.tsx?$/.test(f) && !/\.test\.tsx?$/.test(f));
    expect(sources.length).toBeGreaterThan(5);
    for (const file of sources) {
      const text = readFileSync(join(dir, file), "utf8");
      // An ordered list of slots, or a table from digits to codes, would be a second engine.
      expect(text, file).not.toMatch(/"MORNING"\s*,\s*"AFTERNOON"/);
      expect(text, file).not.toMatch(/"1-1-1-1"|"1-0-1"\s*:|"101"\s*:/);
    }
  });
});

describe("how long (prescriptions R23)", () => {
  it.each([
    ["", { kind: null, days: null }],
    ["5", { kind: "DAYS", days: 5 }],
    ["r", { kind: "UNTIL_REVIEW", days: null }],
    ["Review", { kind: "UNTIL_REVIEW", days: null }],
    ["g", { kind: "ONGOING", days: null }],
    ["ongoing", { kind: "ONGOING", days: null }],
  ])("%j reads as %j", (typed, read) => {
    expect(parseDuration(typed)).toEqual(read);
  });

  it.each(["0", "366", "five", "2w"])("%j is refused", (typed) => {
    expect(parseDuration(typed)).toBeUndefined();
  });
});
describe("the builder's draft", () => {
  const line = toLine({ medicine_name: "Syrup X", dose: "5 ml", frequency: "1-0-1", timing: "AFTER_FOOD", duration_days: 5 });

  it("summarises a line for lists and history", () => {
    expect(lineSummary(line)).toBe("Syrup X · 5 ml · 1-0-1 · after food · 5 days");
    expect(lineSummary({ medicine_name: "Drops", duration_days: 1 })).toBe("Drops · 1 day");
    expect(lineSummary({ medicine_name: "Tab", duration_kind: "UNTIL_REVIEW" })).toBe("Tab · until review");
  });

  it("sends the whole draft without the builder's keys (P2 3A)", () => {
    const body = draftBody({ ...EMPTY_BODY, lines: [line], advice: adviceText({ diet: ["Light food"] }), followUp: "2026-10-25" }, 4);
    expect(body).toEqual({
      revision: 4,
      items: [
        {
          medicine_name: "Syrup X",
          form: null,
          strength: null,
          dose: "5 ml",
          frequency: "1-0-1",
          frequency_text: null,
          timing: "AFTER_FOOD",
          duration_days: 5,
          duration_kind: "DAYS",
          quantity: null,
          preparation: [],
          storage: [],
          warnings: null,
          notes: null,
          favourite_id: null,
        },
      ],
      advice: { diet: ["Light food"], activity: [], return_if: [], notes: null },
      follow_up_date: "2026-10-25",
      template_id: null,
      starts_on: null,
    });
  });

  it("advice is one entry per line, blank lines dropped", () => {
    expect(adviceInput({ diet: " Rice \n\nCurd", activity: "", return_if: "High fever", notes: "  " })).toEqual({
      diet: ["Rice", "Curd"],
      activity: [],
      return_if: ["High fever"],
      notes: null,
    });
  });

  it("a template replaces the body and its follow-up counts from today", () => {
    const body = fromTemplate(
      {
        id: "t1",
        name: "Fever",
        items: [{ medicine_name: "Syrup X" }],
        advice: { diet: [], activity: ["Rest"], return_if: [], notes: null },
        follow_up_days: 7,
        revision: 1,
        use_count: 0,
        last_used_at: null,
        updated_at: "2026-10-01T00:00:00+00:00",
      },
      "2026-10-18",
      addDays,
    );
    expect(body.lines.map((l) => l.medicine_name)).toEqual(["Syrup X"]);
    expect(body.followUp).toBe("2026-10-25");
    expect(body.templateId).toBe("t1");
    expect(daysBetween("2026-10-18", "2026-10-25")).toBe(7);
  });

  it("moves a line one place; past either end nothing changes", () => {
    const a = toLine({ medicine_name: "A" });
    const b = toLine({ medicine_name: "B" });
    expect(moveLine([a, b], 0, 1).map((l) => l.medicine_name)).toEqual(["B", "A"]);
    const same = [a, b];
    expect(moveLine(same, 0, -1)).toBe(same);
    expect(moveLine(same, 1, 1)).toBe(same);
  });

  it("is empty with no lines and no advice", () => {
    expect(isEmpty(EMPTY_BODY)).toBe(true);
    expect(isEmpty({ ...EMPTY_BODY, advice: adviceText({ notes: "Rest" }) })).toBe(false);
  });
});
