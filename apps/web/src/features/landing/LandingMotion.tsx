"use client";

import { useEffect } from "react";

/**
 * The landing page's motion (M7c-P7, M1; DESIGN.md §4, landing-page-design B7 and B11), in a few
 * hundred bytes and no animation library, so the page stays inside its 200 KB budget.
 *
 * - `[data-reveal]` sections rise 32 px and fade in once, as they enter the viewport
 *   (IntersectionObserver). Only sections still below the fold are hidden first, so nothing on
 *   the first screen ever flashes, and without JavaScript everything is simply visible.
 * - `[data-words]` (the tagline): each word turns from the muted tone to full text colour as it
 *   crosses a line 60% down the viewport, read in order (one scroll listener throttled by
 *   requestAnimationFrame). The muted tone is slate-400 (3.4:1, AA for large text).
 *
 * With "reduce motion" nothing moves and every word is at full colour.
 */
export function LandingMotion() {
  useEffect(() => {
    const reduce = typeof window.matchMedia === "function" && window.matchMedia("(prefers-reduced-motion: reduce)").matches;
    if (reduce || typeof IntersectionObserver === "undefined") return;

    const sections = Array.from(document.querySelectorAll<HTMLElement>("[data-reveal]"));
    const below = sections.filter((el) => el.getBoundingClientRect().top > window.innerHeight * 0.9);
    below.forEach((el) => el.setAttribute("data-reveal", "pending"));
    const observer = new IntersectionObserver(
      (entries) => {
        for (const entry of entries) {
          if (entry.isIntersecting) {
            entry.target.setAttribute("data-reveal", "shown");
            observer.unobserve(entry.target);
          }
        }
      },
      { rootMargin: "0px 0px -10% 0px" },
    );
    below.forEach((el) => observer.observe(el));

    const words = Array.from(document.querySelectorAll<HTMLElement>("[data-words] [data-word]"));
    words.forEach((w) => w.setAttribute("data-word", "muted"));
    let frame = 0;
    const paint = () => {
      frame = 0;
      const line = window.innerHeight * 0.6;
      for (const w of words) {
        w.setAttribute("data-word", w.getBoundingClientRect().top < line ? "on" : "muted");
      }
    };
    const onScroll = () => {
      if (frame === 0) frame = window.requestAnimationFrame(paint);
    };
    paint();
    window.addEventListener("scroll", onScroll, { passive: true });
    return () => {
      observer.disconnect();
      window.removeEventListener("scroll", onScroll);
      if (frame !== 0) window.cancelAnimationFrame(frame);
    };
  }, []);
  return null;
}
