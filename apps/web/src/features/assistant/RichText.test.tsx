import { render, screen } from "@testing-library/react";
import { describe, expect, it } from "vitest";

import { blocks, RichText } from "@/features/assistant/RichText";

describe("assistant replies with simple formatting (M7c-P4; spec assistant R21)", () => {
  it("R21 shows bold, italics, bullets and numbered items", () => {
    const { container } = render(
      <RichText text={"**Sessions** you can book:\n- Dr. A, *10:30 AM*\n- Dr. B, 1:00 PM\n\n1. Asha\n2. Ravi"} />,
    );
    expect(screen.getByText("Sessions").tagName).toBe("STRONG");
    expect(screen.getByText("10:30 AM").tagName).toBe("EM");
    expect(container.querySelectorAll("ul > li")).toHaveLength(2);
    const numbered = container.querySelectorAll("ol > li");
    expect([...numbered].map((li) => li.getAttribute("value"))).toEqual(["1", "2"]);
  });

  it("R21 keeps the explanation's shape: numbered medicines with their lines nested", () => {
    const text = "Medicines:\n1. Syrup X\n   - How much: 5 ml\n   - How long: 5 days\n2. Tab Y";
    const [para, list] = blocks(text);
    expect(para).toEqual({ kind: "para", lines: ["Medicines:"] });
    expect(list).toMatchObject({ kind: "list", ordered: true });
    expect(list?.kind === "list" && list.items.map((i) => [i.text, i.level])).toEqual([
      ["Syrup X", 0],
      ["How much: 5 ml", 1],
      ["How long: 5 days", 1],
      ["Tab Y", 0],
    ]);
  });

  it("R21 never renders HTML, links or images; they stay plain text", () => {
    const evil = '<img src=x onerror="alert(1)"> [click](javascript:alert(1)) ![p](http://x/p.png) <b>hi</b>';
    const { container } = render(<RichText text={evil} />);
    expect(container.querySelector("img, a, b, script")).toBeNull();
    expect(container.textContent).toContain('<img src=x onerror="alert(1)">');
    expect(container.textContent).toContain("[click](javascript:alert(1))");
  });

  it("R21 leaves plain text and arithmetic alone", () => {
    const { container } = render(<RichText text={"Take 2 * 3 ml\nthen rest"} />);
    expect(container.querySelector("em, strong")).toBeNull();
    expect(container.querySelectorAll("br")).toHaveLength(1);
    expect(container.textContent).toBe("Take 2 * 3 mlthen rest");
  });
});
