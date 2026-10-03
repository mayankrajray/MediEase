import { afterEach, describe, expect, it, vi } from "vitest";

import {
  CLINIC_STORAGE_KEY,
  forgetClinic,
  readRememberedClinic,
  rememberClinic,
} from "./clinic-selection";
import { CLINIC_A } from "./testing";

afterEach(() => {
  window.localStorage.clear();
});

describe("remembered clinic", () => {
  it("round-trips a clinic ID", () => {
    expect(readRememberedClinic()).toBeNull();
    rememberClinic(CLINIC_A);
    expect(window.localStorage.getItem(CLINIC_STORAGE_KEY)).toBe(CLINIC_A);
    expect(readRememberedClinic()).toBe(CLINIC_A);
  });

  it("forgets it", () => {
    rememberClinic(CLINIC_A);
    forgetClinic();
    expect(readRememberedClinic()).toBeNull();
  });

  it("ignores a tampered value that is not a UUID", () => {
    window.localStorage.setItem(CLINIC_STORAGE_KEY, "<script>alert(1)</script>");
    expect(readRememberedClinic()).toBeNull();
  });

  it("treats blocked storage as 'nothing remembered' instead of throwing", () => {
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => {
      throw new DOMException("blocked", "SecurityError");
    });
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => {
      throw new DOMException("blocked", "SecurityError");
    });
    vi.spyOn(Storage.prototype, "removeItem").mockImplementation(() => {
      throw new DOMException("blocked", "SecurityError");
    });

    expect(readRememberedClinic()).toBeNull();
    expect(() => rememberClinic(CLINIC_A)).not.toThrow();
    expect(() => forgetClinic()).not.toThrow();
  });
});
