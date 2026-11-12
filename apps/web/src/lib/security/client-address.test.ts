// @vitest-environment node
import { describe, expect, it } from "vitest";

import { CLIENT_IP_HEADER, PROXY_SECRET_HEADER, edgeAddress, forwardedFrom, forwardingConfig, withClientAddress } from "./client-address";

/** M7e, A11: the browser's address, from the edge's header only, with the shared secret. */

const SECRET = "a-trusted-proxy-secret-of-at-least-32-chars";
const on = { secret: SECRET, sourceHeader: "x-forwarded-for" };

describe("client address (M7e, A11)", () => {
  it("reads the settings, trimmed, with the header name in lower case", () => {
    expect(forwardingConfig({ TRUSTED_PROXY_SECRET: ` ${SECRET} `, CLIENT_IP_HEADER: " X-Real-IP " })).toEqual({ secret: SECRET, sourceHeader: "x-real-ip" });
    expect(forwardingConfig({})).toEqual({ secret: "", sourceHeader: "" });
  });

  it("takes the last value of the edge's header: anything before it may be the browser's own", () => {
    const headers = new Headers({ "x-forwarded-for": "10.0.0.1, 198.51.100.9 , 203.0.113.7" });
    expect(edgeAddress(headers, "x-forwarded-for")).toBe("203.0.113.7");
    expect(edgeAddress(new Headers({ "x-real-ip": "2001:db8::1" }), "x-real-ip")).toBe("2001:db8::1");
  });

  it("ignores a missing header, an unset source and anything that is not an address", () => {
    expect(edgeAddress(new Headers(), "x-forwarded-for")).toBeUndefined();
    expect(edgeAddress(new Headers({ "x-forwarded-for": "203.0.113.7" }), "")).toBeUndefined();
    for (const bad of ["unknown", "203.0.113.7\r\nX-Evil: 1", "<script>", "a".repeat(60)]) {
      expect(edgeAddress(new Headers({ "x-real-ip": bad.replace(/[\r\n]/g, " ") }), "x-real-ip"), bad).toBeUndefined();
    }
  });

  it("always removes the headers a browser may not set, and adds them only when configured", () => {
    const incoming = new Headers({ [CLIENT_IP_HEADER]: "198.51.100.9", [PROXY_SECRET_HEADER]: "guess", "x-forwarded-for": "203.0.113.7", accept: "x" });
    const off = withClientAddress(incoming, { secret: "", sourceHeader: "x-forwarded-for" });
    expect(off.get(CLIENT_IP_HEADER)).toBeNull();
    expect(off.get(PROXY_SECRET_HEADER)).toBeNull();
    expect(off.get("accept")).toBe("x");
    const set = withClientAddress(incoming, on);
    expect(set.get(CLIENT_IP_HEADER)).toBe("203.0.113.7");
    expect(set.get(PROXY_SECRET_HEADER)).toBe(SECRET);
    // The incoming headers are left as they were.
    expect(incoming.get(CLIENT_IP_HEADER)).toBe("198.51.100.9");
  });

  it("a server-side call carries the two headers only when the proxy set both", () => {
    expect(forwardedFrom(withClientAddress(new Headers({ "x-forwarded-for": "203.0.113.7" }), on))).toEqual({
      [CLIENT_IP_HEADER]: "203.0.113.7",
      [PROXY_SECRET_HEADER]: SECRET,
    });
    expect(forwardedFrom(new Headers({ [CLIENT_IP_HEADER]: "203.0.113.7" }))).toEqual({});
    expect(forwardedFrom(new Headers())).toEqual({});
  });
});
