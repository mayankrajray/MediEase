"use client";

import { useEffect, useId, useRef, useState, type KeyboardEvent } from "react";

export interface MenuItem {
  readonly label: string;
  readonly onSelect: () => void;
}

/**
 * A menu button (WAI-ARIA menu pattern, M3-P5): Enter, Space or ArrowDown opens it with focus on
 * the first item; arrows move, Home/End jump, Escape closes and returns focus to the button,
 * choosing an item closes it. `label` is the button's accessible name and should say whose
 * actions these are ("More actions for Asha Rao").
 */
export function Menu({
  label,
  text = "More",
  items,
}: {
  label: string;
  text?: string;
  items: readonly MenuItem[];
}) {
  const [open, setOpen] = useState(false);
  const [active, setActive] = useState(0);
  const button = useRef<HTMLButtonElement>(null);
  const refs = useRef<(HTMLButtonElement | null)[]>([]);
  const menuId = useId();

  useEffect(() => {
    if (open) refs.current[active]?.focus();
  }, [open, active]);

  useEffect(() => {
    if (!open) return;
    const close = (event: MouseEvent) => {
      const target = event.target as Node;
      if (!button.current?.parentElement?.contains(target)) setOpen(false);
    };
    document.addEventListener("mousedown", close);
    return () => document.removeEventListener("mousedown", close);
  }, [open]);

  function show(index: number) {
    setActive(index);
    setOpen(true);
  }

  function close() {
    setOpen(false);
    button.current?.focus();
  }

  function onMenuKey(event: KeyboardEvent) {
    const last = items.length - 1;
    switch (event.key) {
      case "ArrowDown":
        event.preventDefault();
        setActive((i) => (i >= last ? 0 : i + 1));
        break;
      case "ArrowUp":
        event.preventDefault();
        setActive((i) => (i <= 0 ? last : i - 1));
        break;
      case "Home":
        event.preventDefault();
        setActive(0);
        break;
      case "End":
        event.preventDefault();
        setActive(last);
        break;
      case "Escape":
      case "Tab":
        event.preventDefault();
        close();
        break;
    }
  }

  return (
    <div className="relative inline-block">
      <button
        ref={button}
        type="button"
        aria-label={label}
        aria-haspopup="menu"
        aria-expanded={open}
        aria-controls={open ? menuId : undefined}
        onClick={() => (open ? setOpen(false) : show(0))}
        onKeyDown={(event) => {
          if (event.key === "ArrowDown") {
            event.preventDefault();
            show(0);
          }
        }}
        className="inline-flex min-h-8 items-center justify-center gap-2 rounded-lg border border-slate-400 bg-white px-3 py-1 text-sm font-medium text-slate-900 transition-colors hover:bg-slate-100 disabled:cursor-not-allowed disabled:text-slate-500 motion-reduce:transition-none"
      >
        {text}
      </button>
      {open && (
        <div
          id={menuId}
          role="menu"
          aria-label={label}
          onKeyDown={onMenuKey}
          className="absolute right-0 z-20 mt-1 min-w-40 rounded-lg border border-slate-300 bg-white py-1 shadow-lg"
        >
          {items.map((item, index) => (
            <button
              key={item.label}
              ref={(el) => {
                refs.current[index] = el;
              }}
              type="button"
              role="menuitem"
              tabIndex={index === active ? 0 : -1}
              onClick={() => {
                setOpen(false);
                button.current?.focus();
                item.onSelect();
              }}
              className="block w-full px-4 py-2 text-left hover:bg-slate-100 focus:bg-brand-100"
            >
              {item.label}
            </button>
          ))}
        </div>
      )}
    </div>
  );
}
