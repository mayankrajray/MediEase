import { describe, expect, it } from "vitest";

import { parseCookie, readCsrfToken } from "./csrf";

describe("parseCookie", () => {
  it("finds one cookie among several", () => {
    expect(parseCookie("a=1; me_csrf=tok-en_9; b=2", "me_csrf")).toBe("tok-en_9");
  });

  it("does not match a cookie whose name merely ends with the wanted one", () => {
    expect(parseCookie("x_me_csrf=nope", "me_csrf")).toBeUndefined();
  });

  it("keeps '=' inside a value and decodes percent-escapes", () => {
    expect(parseCookie("me_csrf=a%2Bb==", "me_csrf")).toBe("a+b==");
  });

  it("returns the raw value when it is not valid percent-encoding", () => {
    expect(parseCookie("me_csrf=100%", "me_csrf")).toBe("100%");
  });

  it("is undefined when absent or empty", () => {
    expect(parseCookie("", "me_csrf")).toBeUndefined();
    expect(parseCookie("a=1", "me_csrf")).toBeUndefined();
  });
});

describe("readCsrfToken", () => {
  it("FR-AUTH-01: reads the token from document.cookie in the browser", () => {
    document.cookie = "me_csrf=from-jsdom; path=/";
    expect(readCsrfToken()).toBe("from-jsdom");
    document.cookie = "me_csrf=; path=/; expires=Thu, 01 Jan 1970 00:00:00 GMT";
    expect(readCsrfToken()).toBeUndefined();
  });
});
