"use client";

import dynamic from "next/dynamic";
import { useEffect, useState } from "react";

import type { PwaLanguage } from "@/lib/i18n/pwa";

import { EVENTS, somethingToOffer } from "./signals";

const AppPrompts = dynamic(() => import("./AppPrompts").then((m) => m.AppPrompts), { ssr: false });

/**
 * M7e-E1 (NFR-02, design §7 Q2): loads the prompts only when there is something to offer on this
 * device (an install prompt, an update, or an iPhone without the app), so a normal page load does
 * not download them.
 */
export function AppPromptsGate({ language }: Readonly<{ language: PwaLanguage }>) {
  const [show, setShow] = useState(false);
  useEffect(() => {
    const check = () => {
      if (somethingToOffer()) setShow(true);
    };
    check();
    for (const name of EVENTS) window.addEventListener(name, check);
    return () => {
      for (const name of EVENTS) window.removeEventListener(name, check);
    };
  }, []);
  return show ? <AppPrompts language={language} /> : null;
}
