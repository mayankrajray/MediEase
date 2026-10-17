import { isValidElement, type ReactElement } from "react";
import { afterEach, describe, expect, it, vi } from "vitest";

import { ChallengeForm, LinkProblem } from "@/features/patient-link/ChallengeForm";
import { PrescriptionView } from "@/features/patient-link/PrescriptionView";
import { ApiError } from "@/lib/api/client";

const cookieValue = vi.hoisted(() => ({ current: undefined as string | undefined }));
const apiGet = vi.hoisted(() => vi.fn());

vi.mock("next/headers", () => ({
  cookies: async () => ({ get: () => (cookieValue.current === undefined ? undefined : { value: cookieValue.current }) }),
}));
vi.mock("@/lib/api/client", async (original) => ({ ...(await original<object>()), apiGet }));

const { default: Page } = await import("./page");

async function render(query: Record<string, string> = {}): Promise<ReactElement<Record<string, unknown>>> {
  const element = await Page({ params: Promise.resolve({ token: "a.b.c" }), searchParams: Promise.resolve(query) });
  if (!isValidElement<Record<string, unknown>>(element)) throw new Error("expected an element");
  return element;
}

const SUMMARY = { clinic_name: "Sample Clinic", language: "hi", locked: false, challenge_required: true };

describe("the patient page route (M4-P5, spec R10, R19, decision 5A)", () => {
  afterEach(() => {
    cookieValue.current = undefined;
    apiGet.mockReset();
  });

  it("R10: without a view cookie it asks for the digits, in the patient's saved language", async () => {
    apiGet.mockResolvedValueOnce({ data: SUMMARY });
    const element = await render();
    expect(element.type).toBe(ChallengeForm);
    expect(element.props).toMatchObject({ clinicName: "Sample Clinic", language: "hi", locked: false, switchHref: "/p/a.b.c?lang=en" });
    expect(element.props.problem).toBeUndefined();
  });

  it("R19: ?lang= overrides the saved language for this view only, and a wrong answer is shown", async () => {
    apiGet.mockResolvedValueOnce({ data: SUMMARY });
    const element = await render({ lang: "en", e: "failed", left: "2" });
    expect(element.props).toMatchObject({ language: "en", problem: "Those digits don't match. 2 tries left." });
  });

  it("with this link's view cookie it shows the prescription, sending the token as X-Link-View", async () => {
    cookieValue.current = "view.token";
    apiGet.mockResolvedValueOnce({ data: { language: "en" } });
    const element = await render({ lang: "en" });
    expect(element.type).toBe(PrescriptionView);
    expect(apiGet).toHaveBeenCalledWith("/api/v1/public/links/{token}/prescription", {
      pathParams: { token: "a.b.c" },
      query: { lang: "en" },
      headers: { "X-Link-View": "view.token" },
    });
  });

  it("an ended view asks again", async () => {
    cookieValue.current = "old.view";
    apiGet
      .mockRejectedValueOnce(new ApiError("LINK_CHALLENGE_REQUIRED", "x", 401, "r"))
      .mockResolvedValueOnce({ data: SUMMARY });
    expect((await render()).type).toBe(ChallengeForm);
  });

  it.each([
    ["LINK_INVALID", "This link isn't valid"],
    ["LINK_EXPIRED", "This link has expired"],
    ["LINK_REVOKED", "no longer active"],
  ])("%s shows only a message", async (code, text) => {
    apiGet.mockRejectedValueOnce(new ApiError(code, "x", 404, "r"));
    const element = await render({ lang: "en" });
    expect(element.type).toBe(LinkProblem);
    expect(String(element.props.message)).toContain(text);
  });
});
