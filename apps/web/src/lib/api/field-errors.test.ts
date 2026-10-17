import { describe, expect, it } from "vitest";

import { ApiError } from "./client";
import { fieldErrors } from "./field-errors";

describe("fieldErrors", () => {
  const failed = (details: Record<string, unknown>, code = "REQ_VALIDATION_FAILED") =>
    new ApiError(code, "Some fields are missing or not valid.", 422, "ref-1", details);

  it("reads details.fields into a map by field name", () => {
    expect(
      fieldErrors(
        failed({
          fields: [
            { field: "slug", reason: "slug: must be lower-case words joined by hyphens" },
            { field: "name", reason: "Field required" },
          ],
        }),
      ),
    ).toEqual({
      slug: "slug: must be lower-case words joined by hyphens",
      name: "Field required",
    });
  });

  it("keeps the first reason for a repeated field", () => {
    expect(
      fieldErrors(failed({ fields: [{ field: "name", reason: "first" }, { field: "name", reason: "second" }] })),
    ).toEqual({ name: "first" });
  });

  it("ignores malformed entries, other errors and non-errors", () => {
    expect(fieldErrors(failed({ fields: [{ field: 1 }, "x", null] }))).toEqual({});
    expect(fieldErrors(failed({}))).toEqual({});
    expect(fieldErrors(new ApiError("CLN_SLUG_TAKEN", "taken", 409, "ref"))).toEqual({});
    expect(fieldErrors(new Error("boom"))).toEqual({});
  });

  it("reads other codes only when the caller names them", () => {
    const invalidPhone = failed({ fields: [{ field: "phone", reason: "not a valid phone number" }] }, "PAT_PHONE_INVALID");
    expect(fieldErrors(invalidPhone)).toEqual({});
    expect(fieldErrors(invalidPhone, ["REQ_VALIDATION_FAILED", "PAT_PHONE_INVALID"])).toEqual({
      phone: "not a valid phone number",
    });
  });
});
