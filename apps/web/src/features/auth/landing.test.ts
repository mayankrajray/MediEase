import { describe, expect, it } from "vitest";

import { chooseClinic, postSignInPath, resolveLanding } from "./landing";
import { CLINIC_A, CLINIC_B, membership, ops, person } from "./testing";

const a = membership(CLINIC_A, "Alpha Clinic");
const b = membership(CLINIC_B, "Beta Clinic", "DOCTOR");

describe("chooseClinic (spec R6)", () => {
  it("FR-AUTH-03: no membership means no clinic", () => {
    expect(chooseClinic([], null)).toEqual({ kind: "none" });
  });

  it("FR-AUTH-03: a single membership is used without an X-Clinic-ID header", () => {
    expect(chooseClinic([a], null)).toEqual({ kind: "active", membership: a, sendClinicHeader: false });
  });

  it("a single membership ignores a stale remembered clinic", () => {
    expect(chooseClinic([a], CLINIC_B)).toEqual({
      kind: "active",
      membership: a,
      sendClinicHeader: false,
    });
  });

  it("FR-AUTH-03: several memberships and nothing remembered means the person must choose", () => {
    expect(chooseClinic([a, b], null)).toEqual({ kind: "choose" });
  });

  it("several memberships with a remembered one use it, and send the header", () => {
    expect(chooseClinic([a, b], CLINIC_B)).toEqual({
      kind: "active",
      membership: b,
      sendClinicHeader: true,
    });
  });

  it("a remembered clinic that is no longer a membership is ignored", () => {
    expect(chooseClinic([a, b], "0192f0a0-0000-7000-8000-0000000000ff")).toEqual({ kind: "choose" });
  });
});

describe("resolveLanding", () => {
  it("R10: an ops user lands in the ops console even if they somehow hold a membership", () => {
    expect(resolveLanding(ops(), CLINIC_A)).toEqual({ kind: "ops" });
    expect(resolveLanding(person([a], { is_platform_ops: true }), null)).toEqual({ kind: "ops" });
  });

  it("a clinic user follows chooseClinic", () => {
    expect(resolveLanding(person([a, b]), CLINIC_A)).toMatchObject({ kind: "active" });
  });
});

describe("postSignInPath", () => {
  it("a single-clinic user opens the page they were headed to", () => {
    expect(postSignInPath(person([a]), null, "/queue")).toBe("/queue");
    expect(postSignInPath(person([a]), null, "/patients?x=1")).toBe("/patients?x=1");
  });

  it("a multi-clinic user with a remembered clinic goes straight in", () => {
    expect(postSignInPath(person([a, b]), CLINIC_B, "/queue")).toBe("/queue");
  });

  it("a multi-clinic user with nothing remembered chooses first, keeping the destination", () => {
    expect(postSignInPath(person([a, b]), null, "/today")).toBe("/select-clinic");
    expect(postSignInPath(person([a, b]), null, "/queue")).toBe("/select-clinic?next=%2Fqueue");
    expect(postSignInPath(person([a, b]), null, "/patients?x=1")).toBe(
      "/select-clinic?next=%2Fpatients%3Fx%3D1",
    );
  });

  it("R10: an ops user goes to /ops and may only continue inside it", () => {
    expect(postSignInPath(ops(), null, "/queue")).toBe("/ops");
    expect(postSignInPath(ops(), null, "/ops/clinics")).toBe("/ops/clinics");
    expect(postSignInPath(ops(), null, "/opsy")).toBe("/ops");
  });

  it("a clinic user is never sent into the ops console; they land on Today (M6-P1)", () => {
    expect(postSignInPath(person([a]), null, "/ops/clinics")).toBe("/today");
  });

  it("a person with no clinic lands on the queue, which explains they have no access", () => {
    expect(postSignInPath(person([]), null, "/queue")).toBe("/queue");
  });
});
