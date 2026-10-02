import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { StatusView } from "./StatusView";

describe("StatusView", () => {
  it("NFR-12: healthy shows API healthy, DB ready and the Ref", () => {
    render(<StatusView status={{ state: "healthy", requestId: "ref-ok" }} />);

    const line = screen.getByRole("status");
    expect(line).toHaveTextContent("API: healthy · DB: ready · Ref: ref-ok");
    expect(screen.queryByText(/Code:/)).not.toBeInTheDocument();
  });

  it("NFR-12: degraded shows DB not ready with the API's message, code and Ref", () => {
    render(
      <StatusView
        status={{
          state: "degraded",
          requestId: "ref-db",
          code: "READY_DB_UNAVAILABLE",
          message: "The database is not reachable.",
        }}
      />,
    );

    expect(screen.getByRole("status")).toHaveTextContent("API: healthy · DB: not ready · Ref: ref-db");
    expect(screen.getByText("The database is not reachable.")).toBeInTheDocument();
    expect(screen.getByText("READY_DB_UNAVAILABLE")).toBeInTheDocument();
  });

  it("NFR-12: down shows API unreachable with the code and Ref, never a blank page", () => {
    render(
      <StatusView
        status={{
          state: "down",
          requestId: "ref-down",
          code: "WEB_API_UNREACHABLE",
          message: "The API could not be reached.",
        }}
      />,
    );

    expect(screen.getByRole("status")).toHaveTextContent("API: unreachable · DB: unknown · Ref: ref-down");
    expect(screen.getByText("The API could not be reached.")).toBeInTheDocument();
    expect(screen.getByText("WEB_API_UNREACHABLE")).toBeInTheDocument();
  });

  it("has a page heading and a way to check again", () => {
    render(<StatusView status={{ state: "healthy", requestId: "r" }} />);

    expect(screen.getByRole("heading", { level: 1, name: "System status" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Check again" })).toHaveAttribute("href", "/status");
  });
});
