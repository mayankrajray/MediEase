import { describe, expect, it } from "vitest";

import { formatPaise } from "@/lib/format/money";
import { formatDayTime } from "@/lib/format/time";

import { explainFailure, shouldCall, templateLabel } from "./labels";

describe("failed messages in plain words (M5-P6 decision 5A)", () => {
  it("explains each known code and never shows the code itself", () => {
    expect(explainFailure("FAILED", "MSG_RECIPIENT_INVALID")).toBe("This number can't receive WhatsApp.");
    expect(explainFailure("FAILED", "MSG_OUTCOME_UNKNOWN")).toMatch(/can't tell whether it arrived/);
    expect(explainFailure("FAILED", "REM_CLINIC_PHONE_MISSING")).toMatch(/clinic has no phone/);
    expect(explainFailure("SKIPPED_NO_CONSENT", null)).toMatch(/hasn't agreed/);
    expect(explainFailure("FAILED", "MSG_SOMETHING_NEW")).toBe("The message could not be delivered.");
    expect(explainFailure("FAILED", null)).toBe("The message could not be delivered.");
  });

  it("says nothing when nothing went wrong", () => {
    for (const status of ["SCHEDULED", "SENT", "DELIVERED", "READ", "CANCELLED", "QUEUED"]) {
      expect(explainFailure(status, null)).toBeNull();
      expect(shouldCall(status)).toBe(false);
    }
    expect(shouldCall("FAILED")).toBe(true);
    expect(shouldCall("SKIPPED_NO_CONSENT")).toBe(true);
  });

  it("names each template and falls back for an unknown one", () => {
    expect(templateLabel("follow_up_due")).toBe("Follow-up reminder");
    expect(templateLabel("opt_out_confirmed")).toBe("Reply to their STOP");
    expect(templateLabel("something_else")).toBe("Message");
  });
});

describe("formats", () => {
  it("shows paise as rupees with two decimals (decision 6A)", () => {
    expect(formatPaise(12)).toBe("₹0.12");
    expect(formatPaise(0)).toBe("₹0.00");
    expect(formatPaise(123456)).toBe("₹1,234.56");
  });

  it("shows when a reminder is due on the clinic's calendar and clock", () => {
    expect(formatDayTime("2026-10-19T03:30:00+00:00", "Asia/Kolkata")).toBe("Mon, 19 Oct, 09:00");
    expect(formatDayTime("2026-10-19T20:00:00+00:00", "Asia/Kolkata")).toBe("Tue, 20 Oct, 01:30");
    expect(formatDayTime("not a time", "Asia/Kolkata")).toBe("–");
  });
});
