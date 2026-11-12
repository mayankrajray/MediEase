"use client";

import { Download, Share, X } from "lucide-react";
import { useEffect, useId, useState } from "react";

import { Button } from "@/components/ui/Button";
import { pwaWords, type PwaLanguage } from "@/lib/i18n/pwa";

import { appState, EVENTS, installOffer, remember } from "./signals";

export { PROMPT_KEY } from "./signals";

type Offer = "none" | "install" | "ios";

/**
 * M7e-E1 (design §3 E1): offers to install the app once per device, explains Add to Home Screen
 * on an iPhone (the only way iOS installs a web app), and says when a new version is ready. Shows
 * nothing in the installed app or once the offer has been answered. Loaded by `AppPromptsGate`
 * only when one of these applies, so a normal page load does not carry it (NFR-02).
 */
export function AppPrompts({ language }: Readonly<{ language: PwaLanguage }>) {
  const w = pwaWords(language);
  const titleId = useId();
  const [offer, setOffer] = useState<Offer>("none");
  const [update, setUpdate] = useState(false);
  const [updating, setUpdating] = useState(false);

  useEffect(() => {
    const read = () => {
      setOffer(installOffer());
      setUpdate(appState().waiting !== undefined);
    };
    read();
    for (const name of EVENTS) window.addEventListener(name, read);
    return () => {
      for (const name of EVENTS) window.removeEventListener(name, read);
    };
  }, []);

  function close() {
    remember();
    setOffer("none");
  }

  async function install() {
    const prompt = appState().install;
    close();
    if (prompt === undefined) return;
    appState().install = undefined;
    await prompt.prompt();
    await prompt.userChoice.catch(() => undefined);
  }

  function applyUpdate() {
    const waiting = appState().waiting;
    if (waiting === undefined) return;
    setUpdating(true);
    appState().updating = true; // sw-register.js reloads once the new version takes over
    waiting.postMessage({ type: "SKIP_WAITING" });
  }

  return (
    <>
      {update && (
        <div role="status" className="mb-4 flex flex-wrap items-center justify-between gap-3 rounded-card border border-brand-200 bg-brand-50 p-3 text-slate-900">
          <p className="font-medium">{w.update.body}</p>
          <Button variant="primary" size="lg" onClick={applyUpdate} loading={updating}>
            {w.update.action}
          </Button>
        </div>
      )}
      {offer !== "none" && (
        <section aria-labelledby={titleId} className="relative mb-4 rounded-card border border-line bg-white p-4 pr-12 shadow-card">
          <h2 id={titleId} className="font-semibold text-slate-900">
            {offer === "install" ? w.install.title : w.ios.title}
          </h2>
          {offer === "install" ? (
            <>
              <p className="mt-1 text-slate-700">{w.install.body}</p>
              <div className="mt-3 flex flex-wrap gap-2">
                <Button variant="primary" size="lg" icon={<Download className="size-4" />} onClick={() => void install()}>
                  {w.install.action}
                </Button>
                <Button variant="ghost" size="lg" onClick={close}>
                  {w.install.later}
                </Button>
              </div>
            </>
          ) : (
            <>
              <ol className="mt-2 list-decimal space-y-1 pl-5 text-slate-700">
                {w.ios.steps.map((step, i) => (
                  <li key={step}>
                    {step}
                    {i === 0 && <Share aria-hidden="true" className="ml-1 inline size-4 align-text-bottom text-brand-700" />}
                  </li>
                ))}
              </ol>
              <Button variant="secondary" size="lg" className="mt-3" onClick={close}>
                {w.ios.done}
              </Button>
            </>
          )}
          <button
            type="button"
            aria-label={w.close}
            onClick={close}
            className="absolute right-1 top-1 grid size-11 place-items-center rounded-full text-slate-600 hover:bg-surface-muted hover:text-slate-900"
          >
            <X aria-hidden="true" className="size-5" />
          </button>
        </section>
      )}
    </>
  );
}
