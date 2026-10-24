"use client";

import { useCallback, useId, useState } from "react";

import { ErrorNotice } from "@/features/auth/ErrorNotice";
import type { components } from "@/lib/api/schema";
import { portalGet, portalPut } from "@/lib/auth/portal-session";
import { addDays } from "@/lib/format/time";
import { type PortalStrings, portalCalendarDate } from "@/lib/i18n/portal";

import { usePortalLoad } from "./data";
import { PortalCard, ScreenLoading, usePortal } from "./PortalShell";

type S = components["schemas"];
type Plan = S["MedicinePlan"];
type Entry = S["MedicinePlanEntry"];
type Course = S["MedicineCourse"];
type Reminder = S["MedicineReminder"];

/** How far the day can move from today (the API refuses more, spec R35). */
const WINDOW_DAYS = 30;

/**
 * *My medicines* (M6b-P3; spec R28-R44): *Today* by time of day, then "As the doctor wrote", and
 * *Courses* with the reminder choices. Everything shown is the API's plan, laid out by its engine;
 * this screen interprets no pattern, merges nothing and gives no advice (R28, R29). Every view carries
 * the safety line and *Contact your clinic* (R37).
 */
export function PortalMedicines() {
  const { s } = usePortal();
  const [view, setView] = useState<"today" | "courses">("today");
  const groupId = useId();
  return (
    <div className="space-y-5">
      <h1 className="text-2xl font-bold tracking-tight">{s.medicines.title}</h1>
      <div role="group" aria-labelledby={groupId} className="flex gap-2">
        <span id={groupId} className="sr-only">
          {s.medicines.views}
        </span>
        {(["today", "courses"] as const).map((v) => (
          <button
            key={v}
            type="button"
            aria-pressed={view === v}
            onClick={() => setView(v)}
            className="min-h-11 flex-1 rounded-lg border border-brand-700 px-4 font-semibold text-brand-800 aria-pressed:bg-brand-700 aria-pressed:text-white"
          >
            {s.medicines[v]}
          </button>
        ))}
      </div>
      {view === "today" ? <TodayView /> : <CoursesView />}
    </div>
  );
}

function Safety({ phones }: Readonly<{ phones: readonly { readonly clinic: string; readonly phone: string }[] }>) {
  const { s } = usePortal();
  return (
    <section aria-label={s.medicines.contact} className="space-y-2 rounded-lg border border-slate-300 bg-white p-3">
      <p>{s.medicines.safety}</p>
      <ul className="flex flex-wrap gap-2">
        {phones.map((p) => (
          <li key={p.phone}>
            <a href={`tel:${p.phone}`} className="inline-flex min-h-11 flex-col justify-center rounded-lg bg-brand-700 px-4 py-1 font-semibold text-white">
              {s.medicines.contact}
              {phones.length > 1 && <span className="text-sm font-normal">{p.clinic}</span>}
            </a>
          </li>
        ))}
      </ul>
    </section>
  );
}

function phonesOf(items: readonly { readonly clinic_name: string; readonly clinic_phone_e164: string | null }[]) {
  const seen = new Map<string, string>();
  for (const i of items) if (i.clinic_phone_e164 !== null && !seen.has(i.clinic_phone_e164)) seen.set(i.clinic_phone_e164, i.clinic_name);
  return [...seen.entries()].map(([phone, clinic]) => ({ phone, clinic }));
}

/** The doctor's words for one line (R31): medicine and dose as written, then when and how. */
function LineText({ e }: Readonly<{ e: Pick<Entry, "medicine_name" | "form_strength" | "dose" | "timing" | "how"> }>) {
  return (
    <>
      <p className="font-semibold [overflow-wrap:anywhere]">
        {e.medicine_name}
        {e.form_strength !== null && <span className="font-normal"> ({e.form_strength})</span>}
      </p>
      {e.dose !== null && <p className="[overflow-wrap:anywhere]">{e.dose}</p>}
      {[e.timing, e.how].some((x) => x !== null) && (
        <p className="text-sm text-slate-800 [overflow-wrap:anywhere]">{[e.timing, e.how].filter((x) => x !== null).join(" · ")}</p>
      )}
    </>
  );
}

function EntryItem({ e, s }: Readonly<{ e: Entry; s: PortalStrings }>) {
  const progress = e.days_total !== null ? s.medicines.dayOf(e.day, e.days_total) : e.duration;
  return (
    <li className="space-y-0.5 border-t border-slate-200 py-2 first:border-t-0">
      <LineText e={e} />
      {e.as_written !== null && (
        <p>
          <span className="font-semibold">{s.medicines.asWritten}:</span> {e.as_written}
        </p>
      )}
      <p className="text-sm text-slate-700">
        {progress} · {s.medicines.by(e.doctor_name, e.clinic_name)}
      </p>
      {e.reminder?.enabled === true && <p className="text-sm text-slate-700">{s.medicines.reminderOn(e.reminder.remind_at ?? "")}</p>}
    </li>
  );
}

function TodayView() {
  const { s } = usePortal();
  const [day, setDay] = useState<string | undefined>(undefined);
  const load = useCallback(
    async (): Promise<Plan> => (await portalGet("/api/v1/portal/medicine-plan", day === undefined ? {} : { query: { date: day } })).data,
    [day],
  );
  const loaded = usePortalLoad(load);
  if (loaded.status === "loading") return <ScreenLoading label={s.loading} />;
  if (loaded.status === "failed") return <ErrorNotice error={loaded.error} onRetry={loaded.retry} />;
  const plan = loaded.data;
  const all = [...plan.slots.flatMap((slot) => slot.entries), ...plan.as_written];
  const offset = Math.round((Date.parse(`${plan.date}T00:00:00Z`) - Date.parse(`${plan.today}T00:00:00Z`)) / 86_400_000);
  const button = "min-h-11 rounded-lg border border-slate-400 bg-white px-3 font-medium hover:bg-slate-100 disabled:text-slate-500";

  return (
    <div className="space-y-4">
      {!plan.has_prescriptions ? (
        <p>{s.medicines.empty}</p>
      ) : (
        <>
          <div role="group" aria-label={s.medicines.today} className="flex flex-wrap items-center justify-between gap-2">
            <button type="button" className={button} disabled={offset <= -WINDOW_DAYS} onClick={() => setDay(addDays(plan.date, -1))}>
              {s.medicines.previousDay}
            </button>
            <p className="font-semibold" aria-live="polite">
              {offset === 0 ? `${s.medicines.today} · ` : ""}
              {portalCalendarDate(plan.date, s)}
            </p>
            <button type="button" className={button} disabled={offset >= WINDOW_DAYS} onClick={() => setDay(addDays(plan.date, 1))}>
              {s.medicines.nextDay}
            </button>
          </div>
          {offset !== 0 && (
            <button type="button" className={button} onClick={() => setDay(undefined)}>
              {s.medicines.backToToday}
            </button>
          )}
          {all.length === 0 && <p>{s.medicines.nothingOn}</p>}
          {plan.slots.map((slot) => (
            <PortalCard key={slot.slot} id={`slot-${slot.slot}`} title={`${slot.label} · ${slot.time}`}>
              <ul>
                {slot.entries.map((e) => (
                  <EntryItem key={`${e.prescription_id}-${e.item_id}`} e={e} s={s} />
                ))}
              </ul>
            </PortalCard>
          ))}
          {plan.as_written.length > 0 && (
            <PortalCard id="as-written" title={s.medicines.asWritten}>
              <ul>
                {plan.as_written.map((e) => (
                  <EntryItem key={`${e.prescription_id}-${e.item_id}`} e={e} s={s} />
                ))}
              </ul>
            </PortalCard>
          )}
        </>
      )}
      <Safety phones={phonesOf(all)} />
    </div>
  );
}

async function loadCourses(): Promise<readonly Course[]> {
  return (await portalGet("/api/v1/portal/medicine-plan/courses")).data.items;
}

function CoursesView() {
  const { s } = usePortal();
  const loaded = usePortalLoad(loadCourses);
  const [status, setStatus] = useState("");
  if (loaded.status === "loading") return <ScreenLoading label={s.loading} />;
  if (loaded.status === "failed") return <ErrorNotice error={loaded.error} onRetry={loaded.retry} />;
  const courses = loaded.data;
  return (
    <div className="space-y-4">
      <p role="status" className="min-h-6 text-sm">
        {status}
      </p>
      {courses.length === 0 && <p>{s.medicines.noCourses}</p>}
      {courses.length > 0 && <p className="text-sm text-slate-700">{s.medicines.remindersLater}</p>}
      {courses.map((c) => (
        <PortalCard key={c.prescription_id} id={`course-${c.prescription_id}`} title={s.medicines.by(c.doctor_name, c.clinic_name)}>
          <p className="text-sm text-slate-700">
            {s.medicines.from(portalCalendarDate(c.starts_on, s))}
            {c.ends_on !== null && ` · ${s.medicines.until(portalCalendarDate(c.ends_on, s))}`}
          </p>
          {c.revised && !c.reminders_set && (
            <p role="note" className="rounded border border-amber-700 bg-amber-50 p-2 font-medium">
              {s.medicines.updated}
            </p>
          )}
          <ul>
            {c.lines.map((line) => (
              <li key={line.item_id} className="space-y-1 border-t border-slate-200 py-2 first:border-t-0">
                <LineText e={line} />
                {line.as_written !== null && (
                  <p>
                    <span className="font-semibold">{s.medicines.asWritten}:</span> {line.as_written}
                  </p>
                )}
                <p className="text-sm text-slate-700">
                  {line.duration}
                  {line.ends_on !== null && ` · ${s.medicines.until(portalCalendarDate(line.ends_on, s))}`}
                </p>
                {line.slots.map((slot) => (
                  <ReminderChoice
                    key={slot.slot}
                    prescriptionId={c.prescription_id}
                    itemId={line.item_id}
                    slot={slot}
                    onSaved={() => setStatus(s.medicines.reminderSaved)}
                  />
                ))}
              </li>
            ))}
          </ul>
        </PortalCard>
      ))}
      <Safety phones={phonesOf(courses)} />
    </div>
  );
}

/** R38: on or off, and a preferred time (default the slot's). Never changes the prescription. */
function ReminderChoice({
  prescriptionId,
  itemId,
  slot,
  onSaved,
}: Readonly<{
  prescriptionId: string;
  itemId: string;
  slot: Course["lines"][number]["slots"][number];
  onSaved: () => void;
}>) {
  const { s, leave } = usePortal();
  const id = useId();
  const [reminder, setReminder] = useState<Reminder>(slot.reminder);
  const [time, setTime] = useState(slot.reminder.remind_at ?? slot.time);
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);

  async function save(next: { enabled: boolean; remind_at: string | null }) {
    if (busy) return;
    const before = reminder;
    // Shown at once; put back if the API refuses it.
    setReminder({ enabled: next.enabled, remind_at: next.remind_at });
    setBusy(true);
    setError(null);
    try {
      const { data } = await portalPut("/api/v1/portal/medicine-plan/reminders", {
        prescription_id: prescriptionId,
        item_id: itemId,
        slot: slot.slot,
        enabled: next.enabled,
        remind_at: next.remind_at,
      });
      setReminder(data);
      onSaved();
    } catch (failure) {
      setReminder(before);
      if (!leave(failure)) setError(failure);
    } finally {
      setBusy(false);
    }
  }

  const chosen = (value: string) => (value === slot.time ? null : value);
  return (
    <div className="space-y-1 rounded-lg bg-slate-50 p-2">
      <label className="flex min-h-11 items-center gap-2">
        <input
          type="checkbox"
          className="size-5"
          checked={reminder.enabled}
          disabled={busy}
          onChange={(e) => void save({ enabled: e.target.checked, remind_at: chosen(time) })}
        />
        {s.medicines.remindMe(slot.label, slot.time)}
      </label>
      {reminder.enabled && (
        <div className="flex flex-wrap items-center gap-2 pl-7">
          <label htmlFor={id} className="text-sm font-medium">
            {s.medicines.reminderTime(slot.label)}
          </label>
          <input
            id={id}
            type="time"
            min="05:00"
            max="23:30"
            step={60}
            value={time}
            onChange={(e) => setTime(e.target.value)}
            className="min-h-11 rounded-lg border border-slate-400 px-2"
          />
          {(reminder.remind_at ?? slot.time) !== time && time !== "" && (
            <button
              type="button"
              disabled={busy}
              onClick={() => void save({ enabled: true, remind_at: chosen(time) })}
              className="min-h-11 rounded-lg border border-brand-700 bg-white px-3 font-semibold text-brand-800 hover:bg-brand-50"
            >
              {s.medicines.saveTime}
            </button>
          )}
        </div>
      )}
      {error !== null && <ErrorNotice error={error} />}
    </div>
  );
}
