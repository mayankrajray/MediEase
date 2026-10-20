import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { Button } from "./Button";
import { Card } from "./Card";
import { EmptyState } from "./EmptyState";
import { MotionProvider, STAGGER, m } from "./Motion";
import { StatTile } from "./StatTile";
import { StatusBadge } from "./StatusBadge";
import { Tabs } from "./Tabs";

describe("design system primitives (M6-P1)", () => {
  it("a Button never submits a form unless asked to", () => {
    const submit = vi.fn((event: Event) => event.preventDefault());
    render(
      <form onSubmit={(e) => submit(e.nativeEvent)}>
        <Button>Plain</Button>
        <Button type="submit" variant="primary">
          Save
        </Button>
      </form>,
    );
    fireEvent.click(screen.getByRole("button", { name: "Plain" }));
    expect(submit).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "Save" }));
    expect(submit).toHaveBeenCalledTimes(1);
  });

  it("a titled Card is a region named by its heading", () => {
    render(<Card title="Next up">body</Card>);
    expect(screen.getByRole("region", { name: "Next up" })).toHaveTextContent("body");
  });

  it("a StatusBadge says its status in words (never colour alone)", () => {
    render(<StatusBadge tone="waiting">Waiting</StatusBadge>);
    expect(screen.getByText("Waiting")).toBeVisible();
  });

  it("a StatTile with href is one link named by its label and number; without, plain text", () => {
    render(
      <MotionProvider>
        <m.ul variants={STAGGER} initial="hidden" animate="shown">
          <StatTile label="Waiting" value={3} href="/queue" tone="waiting" />
          <StatTile label="Failed" value={0} />
        </m.ul>
      </MotionProvider>,
    );
    expect(screen.getByRole("link", { name: /Waiting\s*3/ })).toHaveAttribute("href", "/queue");
    expect(screen.getAllByRole("link")).toHaveLength(1);
    expect(screen.getByText("Failed")).toBeInTheDocument();
  });

  it("an EmptyState offers the next step", () => {
    render(<EmptyState title="No sessions today" action={<Button>Add a session</Button>} />);
    expect(screen.getByRole("button", { name: "Add a session" })).toBeInTheDocument();
  });

  it("Tabs (Radix): the ARIA tabs pattern, with the mouse and with arrow keys", async () => {
    render(
      <Tabs
        label="Views"
        items={[
          { value: "a", label: "First", content: <p>first panel</p> },
          { value: "b", label: "Second", content: <p>second panel</p> },
        ]}
      />,
    );
    const first = screen.getByRole("tab", { name: "First" });
    const second = screen.getByRole("tab", { name: "Second" });
    expect(screen.getByRole("tablist", { name: "Views" })).toBeInTheDocument();
    expect(first).toHaveAttribute("aria-selected", "true");
    expect(screen.getByRole("tabpanel")).toHaveTextContent("first panel");

    fireEvent.mouseDown(second);
    expect(second).toHaveAttribute("aria-selected", "true");
    expect(screen.getByRole("tabpanel")).toHaveTextContent("second panel");

    second.focus();
    fireEvent.keyDown(second, { key: "ArrowRight" }); // wraps round to the first
    await waitFor(() => expect(first).toHaveAttribute("aria-selected", "true"));
    expect(first).toHaveFocus();
  });
});
