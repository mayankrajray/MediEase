import { describe, expect, it } from "vitest";

import { addDays } from "@/lib/format/time";

import { adviceInput, adviceText, daysBetween, draftBody, fromTemplate, isEmpty, moveLine, toLine, EMPTY_BODY } from "./draft";
import { frequencyLabel, lineSummary, parseFrequency } from "./vocabulary";

describe("frequency shortcuts (spec §6)", () => {
  it.each([
    ["101", "1-0-1"],
    ["1-0-1", "1-0-1"],
    ["1 0 1", "1-0-1"],
    ["100", "1-0-0"],
    ["001", "0-0-1"],
    ["111", "1-1-1"],
    ["1111", "1-1-1-1"],
    ["s", "SOS"],
    ["SOS", "SOS"],
    ["o", "ONCE"],
    ["once", "ONCE"],
    ["C", "CUSTOM"],
  ])("%s reads as %s", (typed, code) => {
    expect(parseFrequency(typed)).toBe(code);
  });

  it.each(["", "  ", "1x", "202", "daily"])("%j is not a code", (typed) => {
    expect(parseFrequency(typed)).toBeUndefined();
  });

  it("labels say the code and its meaning; a custom one is the doctor's words", () => {
    expect(frequencyLabel("1-0-1", null)).toBe("1-0-1 · morning and night");
    expect(frequencyLabel("CUSTOM", "every other day")).toBe("every other day");
  });
});

describe("the builder's draft", () => {
  const line = toLine({ medicine_name: "Syrup X", dose: "5 ml", frequency: "1-0-1", timing: "AFTER_FOOD", duration_days: 5 });

  it("summarises a line for lists and history", () => {
    expect(lineSummary(line)).toBe("Syrup X · 5 ml · 1-0-1 · after food · 5 days");
    expect(lineSummary({ medicine_name: "Drops", duration_days: 1 })).toBe("Drops · 1 day");
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
