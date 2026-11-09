import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";

import { ConfirmDialog } from "@/components/ConfirmDialog";
import { Alert } from "./Alert";
import { Avatar, initials } from "./Avatar";
import { Breadcrumbs } from "./Breadcrumbs";
import { Button } from "./Button";
import { cx } from "./cx";
import { ErrorSummary, TextField } from "./Field";
import { KeyValue } from "./KeyValue";
import { Logo } from "./Logo";
import { Pagination } from "./Pagination";
import { ToastProvider, useToast } from "./Toast";

describe("design system (M7c-P7; DESIGN.md)", () => {
  it("a caller's class is added after the component's own", () => {
    expect(cx("px-4", false, "w-full")).toBe("px-4 w-full");
    render(<Button className="w-full">Wide</Button>);
    expect(screen.getByRole("button", { name: "Wide" }).className).toContain("w-full");
  });

  it("a loading Button keeps its name, is busy and cannot be clicked twice", () => {
    const click = vi.fn();
    render(
      <Button loading onClick={click}>
        Save
      </Button>,
    );
    const button = screen.getByRole("button", { name: "Save" });
    expect(button).toBeDisabled();
    expect(button).toHaveAttribute("aria-busy", "true");
    fireEvent.click(button);
    expect(click).not.toHaveBeenCalled();
  });

  it("the Logo reads MediEase once; compact keeps the name for screen readers", () => {
    const { container } = render(<Logo compact />);
    expect(screen.getByText("MediEase")).toBeInTheDocument();
    expect(container.querySelector("svg")).toHaveAttribute("aria-hidden", "true");
  });

  it("an error links its field and the summary links to the field", () => {
    render(
      <>
        <ErrorSummary errors={[{ id: "phone", message: "Enter a 10-digit mobile number." }]} />
        <TextField id="phone" label="Mobile" value="98" onChange={() => undefined} error="Enter a 10-digit mobile number." />
      </>,
    );
    expect(screen.getByRole("alert")).toHaveTextContent("Please correct these fields");
    expect(screen.getByRole("link", { name: "Enter a 10-digit mobile number." })).toHaveAttribute("href", "#phone");
    const input = screen.getByLabelText("Mobile");
    expect(input).toHaveAttribute("aria-invalid", "true");
    expect(input).toHaveAccessibleDescription("Enter a 10-digit mobile number.");
  });

  it("ErrorSummary renders nothing without errors", () => {
    const { container } = render(<ErrorSummary errors={[]} />);
    expect(container).toBeEmptyDOMElement();
  });

  it("an Alert says its message in words, with the role asked for", () => {
    render(
      <Alert tone="warning" title="Two bookings to move" role="status">
        Dr. Iyer is on leave.
      </Alert>,
    );
    expect(screen.getByRole("status")).toHaveTextContent("Two bookings to moveDr. Iyer is on leave.");
  });

  it("Breadcrumbs link the way back and mark the current page", () => {
    render(<Breadcrumbs items={[{ label: "Patients", href: "/patients" }, { label: "Asha Rao" }]} />);
    expect(screen.getByRole("link", { name: "Patients" })).toHaveAttribute("href", "/patients");
    expect(screen.getByText("Asha Rao")).toHaveAttribute("aria-current", "page");
  });

  it("Pagination says where it is and stops at the ends", () => {
    const onPage = vi.fn();
    const { rerender } = render(<Pagination page={1} total={3} onPage={onPage} />);
    expect(screen.getByText("Page 1 of 3")).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Previous" })).toBeDisabled();
    fireEvent.click(screen.getByRole("button", { name: "Next" }));
    expect(onPage).toHaveBeenCalledWith(2);
    rerender(<Pagination page={3} total={3} onPage={onPage} />);
    expect(screen.getByRole("button", { name: "Next" })).toBeDisabled();
  });

  it("Avatar initials skip titles; KeyValue says a missing value in words", () => {
    expect(initials("Dr. Meera Iyer")).toBe("MI");
    expect(initials("asha")).toBe("A");
    render(
      <>
        <Avatar name="Asha Rao" />
        <KeyValue items={[{ label: "Allergies", value: null }]} />
      </>,
    );
    expect(screen.getByText("Not recorded")).toBeInTheDocument();
  });

  it("ConfirmDialog names its action, starts on the safe choice and confirms only on click", () => {
    const confirm = vi.fn();
    const close = vi.fn();
    render(
      <ConfirmDialog title="Cancel this appointment?" confirmLabel="Cancel appointment" danger onConfirm={confirm} onClose={close}>
        Asha Rao will be told.
      </ConfirmDialog>,
    );
    expect(screen.getByRole("dialog", { name: "Cancel this appointment?" })).toBeInTheDocument();
    expect(screen.getByRole("button", { name: "Keep it" })).toHaveFocus();
    fireEvent.click(screen.getByRole("button", { name: "Keep it" }));
    expect(close).toHaveBeenCalled();
    expect(confirm).not.toHaveBeenCalled();
    fireEvent.click(screen.getByRole("button", { name: "Cancel appointment" }));
    expect(confirm).toHaveBeenCalledTimes(1);
  });

  it("a toast announces a finished action and can be dismissed", async () => {
    function Book() {
      const toast = useToast();
      return <Button onClick={() => toast({ title: "Appointment booked" })}>Book</Button>;
    }
    render(
      <ToastProvider>
        <Book />
      </ToastProvider>,
    );
    fireEvent.click(screen.getByRole("button", { name: "Book" }));
    expect(await screen.findByText("Appointment booked")).toBeInTheDocument();
    fireEvent.click(screen.getByRole("button", { name: "Dismiss" }));
    await waitFor(() => expect(screen.queryByText("Appointment booked")).not.toBeInTheDocument());
  });
});
