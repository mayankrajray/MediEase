import { render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { Dialog } from "./Dialog";
import { Drawer } from "./Drawer";

// A child's own focus() runs before the modal opens and did not stick under jsdom 30.1.2 (the
// booking test failed in CI). A field marked data-autofocus must have the focus once the modal is
// open (the booking drawer's patient search, M3-P5).
describe("modal focus (M3-P5 fix)", () => {
  it("Drawer: a data-autofocus field has the focus once the panel is open", () => {
    render(
      <Drawer title="Book appointment" onClose={vi.fn()}>
        <label htmlFor="q">Patient</label>
        <input id="q" data-autofocus />
      </Drawer>,
    );
    expect(screen.getByLabelText("Patient")).toHaveFocus();
  });

  it("Dialog: the same, and without one the browser's choice stands", () => {
    const { unmount } = render(
      <Dialog title="Cancel" onClose={vi.fn()}>
        <button type="button">First</button>
        <input aria-label="Note" data-autofocus />
      </Dialog>,
    );
    expect(screen.getByLabelText("Note")).toHaveFocus();
    unmount();

    render(
      <Dialog title="Confirm" onClose={vi.fn()}>
        <button type="button">First</button>
      </Dialog>,
    );
    expect(screen.getByRole("button", { name: "First" })).not.toHaveAttribute("data-autofocus");
  });
});
