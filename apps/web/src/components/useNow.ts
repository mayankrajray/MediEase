"use client";

import { useEffect, useState } from "react";

/**
 * The current time, refreshed every `intervalMs` (default a minute), so screens that compare
 * against "now" (which slots have ended, who is waiting, is a session running) stay right without
 * reading the clock during render.
 */
export function useNow(intervalMs = 60_000): number {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const timer = setInterval(() => setNow(Date.now()), intervalMs);
    return () => clearInterval(timer);
  }, [intervalMs]);
  return now;
}
