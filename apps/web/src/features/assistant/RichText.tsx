import type { ReactNode } from "react";

/**
 * An assistant reply with simple formatting (M7c-P4; spec assistant R21).
 *
 * Only a small Markdown subset is understood: **bold**, *italics*, `-`/`*`/`•` bullets and `1.`
 * numbered items (indented items are nested one step), `#` headings shown as bold lines, and blank
 * lines between paragraphs. Everything becomes React elements from plain strings, so nothing is
 * ever parsed as HTML: links, images, tables and tags stay visible as the text they are. A reply
 * without any of these reads exactly as before.
 */

type Block =
  | { kind: "para"; lines: string[] }
  | { kind: "list"; ordered: boolean; items: { text: string; level: number; value?: number }[] };

const BULLET = /^(\s*)[-*•]\s+(.*)$/;
const NUMBERED = /^(\s*)(\d{1,3})[.)]\s+(.*)$/;
const HEADING = /^\s{0,3}#{1,6}\s+(.*)$/;
// **bold** first, then *italics* (not across spaces at the edges, so "2 * 3" stays as it is).
const INLINE = /(\*\*[^*\n]+\*\*|\*[^*\s](?:[^*\n]*[^*\s])?\*)/g;

function level(indent: string): number {
  return indent.replace(/\t/g, "  ").length >= 2 ? 1 : 0;
}

export function blocks(text: string): Block[] {
  const out: Block[] = [];
  let fresh = true; // the next text line starts a new paragraph
  for (const raw of text.replace(/\r\n?/g, "\n").split("\n")) {
    if (raw.trim() === "") {
      fresh = true;
      continue;
    }
    const bullet = BULLET.exec(raw);
    const numbered = bullet ? null : NUMBERED.exec(raw);
    const last = out.at(-1);
    if (bullet || numbered) {
      const ordered = numbered !== null;
      const item = numbered
        ? { text: numbered[3] ?? "", level: level(numbered[1] ?? ""), value: Number(numbered[2]) }
        : { text: bullet?.[2] ?? "", level: level(bullet?.[1] ?? "") };
      // A nested bullet under a numbered item stays in that list (the explanation's shape).
      if (last?.kind === "list" && (last.ordered === ordered || item.level > 0)) {
        last.items.push(item);
      } else {
        out.push({ kind: "list", ordered, items: [item] });
      }
      fresh = true;
      continue;
    }
    const heading = HEADING.exec(raw);
    const line = heading ? `**${heading[1] ?? ""}**` : raw.trim();
    if (!fresh && last?.kind === "para") last.lines.push(line);
    else out.push({ kind: "para", lines: [line] });
    fresh = heading !== null;
  }
  return out;
}

export function inline(text: string): ReactNode[] {
  return text.split(INLINE).map((part, index) => {
    if (part.startsWith("**") && part.endsWith("**") && part.length > 4) {
      return <strong key={index}>{part.slice(2, -2)}</strong>;
    }
    if (part.startsWith("*") && part.endsWith("*") && part.length > 2) {
      return <em key={index}>{part.slice(1, -1)}</em>;
    }
    return part;
  });
}

export function RichText({ text }: Readonly<{ text: string }>) {
  return (
    <div className="space-y-2 break-words">
      {blocks(text).map((block, index) =>
        block.kind === "para" ? (
          <p key={index}>
            {block.lines.map((line, n) => (
              <span key={n}>
                {n > 0 && <br />}
                {inline(line)}
              </span>
            ))}
          </p>
        ) : block.ordered ? (
          <ol key={index} className="space-y-1 pl-5">
            {block.items.map((item, n) => (
              <li
                key={n}
                value={item.value}
                className={item.level > 0 ? "ml-4 list-[circle]" : "list-decimal"}
              >
                {inline(item.text)}
              </li>
            ))}
          </ol>
        ) : (
          <ul key={index} className="space-y-1 pl-5">
            {block.items.map((item, n) => (
              <li key={n} className={item.level > 0 ? "ml-4 list-[circle]" : "list-disc"}>
                {inline(item.text)}
              </li>
            ))}
          </ul>
        ),
      )}
    </div>
  );
}
