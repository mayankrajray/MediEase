import { describe, expect, it } from "vitest";

import { ApiError, WEB_API_BAD_RESPONSE, WEB_API_UNREACHABLE } from "@/lib/api/client";

import {
  describeError,
  formatWait,
  isRetryable,
  parseSignInReason,
  reasonForEndedSession,
} from "./messages";

const err = (code: string, status: number) => new ApiError(code, `msg for ${code}`, status, "ref-1");

describe("parseSignInReason (?reason= is attacker-controllable)", () => {
  it("accepts only the allow-listed reasons", () => {
    expect(parseSignInReason("session_ended")).toBe("session_ended");
    expect(parseSignInReason("account_disabled")).toBe("account_disabled");
    expect(parseSignInReason("session_ended_for_safety")).toBe("session_ended_for_safety");
  });

  it.each([null, undefined, "", "constructor", "__proto__", "toString", "<b>hi</b>", "Session_Ended"])(
    "rejects %j",
    (raw) => {
      expect(parseSignInReason(raw)).toBeUndefined();
    },
  );
});

describe("reasonForEndedSession", () => {
  it("R5, R7: maps the session-ending API codes to a sign-in reason", () => {
    expect(reasonForEndedSession(err("AUTH_SESSION_EXPIRED", 401))).toBe("session_ended");
    expect(reasonForEndedSession(err("AUTH_REFRESH_REUSED", 401))).toBe("session_ended_for_safety");
    expect(reasonForEndedSession(err("AUTH_ACCOUNT_DISABLED", 403))).toBe("account_disabled");
  });

  it("is undefined for anything else", () => {
    expect(reasonForEndedSession(err("PERM_DENIED", 403))).toBeUndefined();
    expect(reasonForEndedSession(new Error("boom"))).toBeUndefined();
  });
});

describe("formatWait", () => {
  it.each([
    [1, "1 second"],
    [30, "30 seconds"],
    [59.2, "1 minute"],
    [60, "1 minute"],
    [61, "2 minutes"],
    [840, "14 minutes"],
    [900, "15 minutes"],
    [0, "1 second"],
    [-5, "1 second"],
  ])("%s seconds -> %s (rounded up)", (seconds, text) => {
    expect(formatWait(seconds)).toBe(text);
  });
});

describe("describeError and isRetryable", () => {
  it("shows the API's message and request ID", () => {
    expect(describeError(err("AUTH_INVALID_CREDENTIALS", 401))).toEqual({
      message: "msg for AUTH_INVALID_CREDENTIALS",
      requestId: "ref-1",
      code: "AUTH_INVALID_CREDENTIALS",
    });
  });

  it("gives an unexpected error a generic message and no leaked detail", () => {
    const text = describeError(new TypeError("Cannot read properties of undefined"));
    expect(text.message).toBe("Something went wrong. Please try again.");
    expect(text.message).not.toMatch(/undefined/);
  });

  it("offers Try again for unreachable, unreadable and 5xx, not for rejections", () => {
    expect(isRetryable(err(WEB_API_UNREACHABLE, 0))).toBe(true);
    expect(isRetryable(err(WEB_API_BAD_RESPONSE, 502))).toBe(true);
    expect(isRetryable(err("INTERNAL", 500))).toBe(true);
    expect(isRetryable(err("AUTH_INVALID_CREDENTIALS", 401))).toBe(false);
    expect(isRetryable(err("AUTH_LOCKED", 423))).toBe(false);
  });
});
