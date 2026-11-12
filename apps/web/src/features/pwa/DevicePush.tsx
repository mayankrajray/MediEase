"use client";

import { useEffect, useRef, useState } from "react";

import { Button } from "@/components/ui/Button";
import { ErrorNotice } from "@/features/auth/ErrorNotice";
import { ApiError } from "@/lib/api/client";
import type { DeviceWords } from "@/lib/i18n/push";

import {
  currentSubscription,
  type Owner,
  permission,
  type PushDevice,
  type PushSubscriptionIn,
  pushSupport,
  rememberDevice,
  storedDevice,
  subscribe,
  unsubscribe,
} from "./push";

/** The calls one kind of person makes for their own devices (portal or staff session). */
export interface PushApi {
  readonly config: () => Promise<{ readonly enabled: boolean; readonly public_key: string | null }>;
  readonly list: () => Promise<readonly PushDevice[]>;
  readonly add: (body: PushSubscriptionIn) => Promise<PushDevice>;
  readonly remove: (id: string) => Promise<void>;
}

type State = "checking" | "on" | "off" | "blocked" | "unsupported" | "ios-install" | "not-offered";

/**
 * M7e-E5 (spec web-push R50-R54): pop-up alerts on *this* device, on or off. The browser asks
 * for permission only after "Turn on" is pressed (R51); a browser that blocks alerts, cannot show
 * them, or (iPhone) is not the installed app says so in words instead of offering a switch that
 * cannot work (R52). Which kinds alert is chosen per kind, beside the in-app switches.
 */
export function DevicePush({
  owner,
  words,
  api,
  onSessionError,
  onSaved,
}: Readonly<{
  owner: Owner;
  words: DeviceWords;
  api: PushApi;
  /** True when the failure ended the session and was handled (sign-in again). */
  onSessionError: (failure: unknown) => boolean;
  onSaved: (text: string) => void;
}>) {
  const [state, setState] = useState<State>("checking");
  const [key, setKey] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const [message, setMessage] = useState<string | undefined>(undefined);
  // The parent's handler may be a new function on every render; the check runs once per owner.
  const sessionError = useRef(onSessionError);
  useEffect(() => {
    sessionError.current = onSessionError;
  }, [onSessionError]);

  useEffect(() => {
    let cancelled = false;
    async function check(): Promise<State> {
      const support = pushSupport();
      if (support !== "supported") return support;
      const config = await api.config();
      if (!config.enabled || config.public_key === null) return "not-offered";
      if (!cancelled) setKey(config.public_key);
      if (permission() === "denied") return "blocked";
      const id = storedDevice(owner);
      if (id === null || (await currentSubscription()) === null) return "off";
      const mine = (await api.list()).find((d) => d.id === id);
      if (mine?.active === true) return "on";
      rememberDevice(owner, null); // removed elsewhere, expired, or now another person's
      return "off";
    }
    check().then(
      (found) => {
        if (!cancelled) setState(found);
      },
      (failure: unknown) => {
        if (cancelled || sessionError.current(failure)) return;
        setState("off");
        setError(failure);
      },
    );
    return () => {
      cancelled = true;
    };
  }, [api, owner]);

  async function run(action: () => Promise<State>, done: string) {
    if (busy) return;
    setBusy(true);
    setError(null);
    setMessage(undefined);
    try {
      const next = await action();
      setState(next);
      if (next === "on" || next === "off") onSaved(done);
    } catch (failure) {
      if (onSessionError(failure)) return;
      setError(failure);
      if (failure instanceof ApiError && failure.code === "PSH_TOO_MANY_DEVICES") setMessage(words.tooMany);
    } finally {
      setBusy(false);
    }
  }

  async function turnOn(): Promise<State> {
    if (key === null) return "not-offered";
    const result = await subscribe(key);
    if (result.kind === "blocked") return "blocked";
    if (result.kind === "unavailable") return "unsupported";
    const device = await api.add(result.body);
    rememberDevice(owner, device.id);
    return "on";
  }

  async function turnOff(): Promise<State> {
    const id = storedDevice(owner);
    if (id !== null) {
      try {
        await api.remove(id);
      } catch (failure) {
        // Already gone (removed on another screen, or now another person's): off either way.
        if (!(failure instanceof ApiError && failure.status === 404)) throw failure;
      }
    }
    rememberDevice(owner, null);
    await unsubscribe();
    return "off";
  }

  const explanation: Partial<Record<State, string>> = {
    blocked: words.blocked,
    unsupported: words.unsupported,
    "ios-install": words.iosInstall,
    "not-offered": words.notOffered,
  };

  return (
    <div className="space-y-3">
      <p className="text-sm text-slate-700">{words.help}</p>
      {state === "checking" && (
        <p role="status" className="text-sm text-slate-700">
          {words.checking}
        </p>
      )}
      {(state === "on" || state === "off") && (
        <div className="flex flex-wrap items-center gap-3">
          <p className="font-medium text-slate-900">{state === "on" ? words.on : words.off}</p>
          <Button
            variant={state === "on" ? "secondary" : "primary"}
            loading={busy}
            className="min-h-11"
            onClick={() => void (state === "on" ? run(turnOff, words.turnedOff) : run(turnOn, words.turnedOn))}
          >
            {state === "on" ? words.turnOff : words.turnOn}
          </Button>
        </div>
      )}
      {explanation[state] !== undefined && (
        <p className="rounded-lg border border-line bg-slate-50 p-3 text-slate-900">{explanation[state]}</p>
      )}
      {error !== null && (message === undefined ? <ErrorNotice error={error} /> : <ErrorNotice error={error} message={message} />)}
    </div>
  );
}
