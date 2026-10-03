import { describe, expect, it } from "vitest";

import { ApiError } from "@/lib/api/client";

import { emptyToNull, fieldErrors, parseSpecialties, suggestSlug } from "./fields";

describe("suggestSlug", () => {
  it.each([
    ["Sample Clinic", "sample-clinic"],
    ["  Dr. Rao's  Children & Family Clinic  ", "dr-rao-s-children-family-clinic"],
    ["Clínica Niño", "clinica-nino"],
    ["---A---", "a"],
    ["", ""],
    ["日本語", ""],
  ])("%j -> %j", (name, slug) => {
    expect(suggestSlug(name)).toBe(slug);
  });

  it("stays within the API's 63-character limit without a trailing hyphen", () => {
    const slug = suggestSlug(`${"a".repeat(62)} b`);
    expect(slug.length).toBeLessThanOrEqual(63);
    expect(slug.endsWith("-")).toBe(false);
  });
});

describe("parseSpecialties", () => {
  it("splits on commas, trims, drops empties and repeats", () => {
    expect(parseSpecialties(" General Medicine, ,Paediatrics,General Medicine ,")).toEqual([
      "General Medicine",
      "Paediatrics",
    ]);
  });

  it("is empty for empty text and capped at the API's limit of 20", () => {
    expect(parseSpecialties("")).toEqual([]);
    const many = Array.from({ length: 30 }, (_, n) => `S${n}`).join(",");
    expect(parseSpecialties(many)).toHaveLength(20);
  });
});

describe("emptyToNull", () => {
  it("sends null for blank optional fields and trims the rest", () => {
    expect(emptyToNull("   ")).toBeNull();
    expect(emptyToNull(" 560001 ")).toBe("560001");
  });
});

describe("fieldErrors", () => {
  const failed = (details: Record<string, unknown>) =>
    new ApiError("REQ_VALIDATION_FAILED", "Some fields are missing or not valid.", 422, "ref-1", details);

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
});
