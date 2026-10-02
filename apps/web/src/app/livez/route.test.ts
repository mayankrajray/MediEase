// @vitest-environment node
import { describe, expect, it, vi } from "vitest";

import { GET } from "./route";

describe("GET /livez", () => {
  it("NFR-15: answers 200 ok without calling the API", async () => {
    const fetchSpy = vi.spyOn(globalThis, "fetch");

    const response = GET();

    expect(response.status).toBe(200);
    expect(await response.json()).toEqual({ status: "ok" });
    expect(response.headers.get("Cache-Control")).toBe("no-store");
    expect(fetchSpy).not.toHaveBeenCalled();
  });
});
