"use client";

import {
  CalendarDays,
  ChevronLeft,
  ChevronRight,
  Info,
  Moon,
  Phone,
  Pill,
  Sun,
  Sunrise,
  Sunset,
} from "lucide-react";
import { useCallback, useId, useState } from "react";

import { Button, buttonClasses } from "@/components/ui/Button";
import { EmptyState } from "@/components/ui/EmptyState";
import { INPUT_BASE } from "@/components/ui/Field";
import { StatusBadge, type Tone } from "@/components/ui/StatusBadge";
import { ErrorNotice } from "@/features/auth/ErrorNotice";
import type { components } from "@/lib/api/schema";
import { portalDelete, portalGet, portalPut } from "@/lib/auth/portal-session";
import { addDays } from "@/lib/format/time";
import { type PortalStrings, portalCalendarDate, portalTime } from "@/lib/i18n/portal";

import { portalErrorText, usePortalLoad } from "./data";
import { PortalCard, PortalTitle, ScreenLoading, usePortal } from "./PortalShell";

type S = components["schemas"];
type Plan = S["MedicinePlan"];
type Entry = S["MedicinePlanEntry"];
type Course = S["MedicineCourse"];
type Reminder = S["MedicineReminder"];
type Mark = S["MedicineDose"];
type History = S["DoseHistory"];
type Slot = S["Slot"];

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
      <PortalTitle>{s.medicines.title}</PortalTitle>
      <div role="group" aria-labelledby={groupId} className="grid grid-cols-2 gap-1 rounded-xl border border-line bg-white p-1 shadow-card">
        <span id={groupId} className="sr-only">
          {s.medicines.views}
        </span>
        {(["today", "courses"] as const).map((v) => (
          <button
            key={v}
            type="button"
            aria-pressed={view === v}
            onClick={() => setView(v)}
            className="inline-flex min-h-11 items-center justify-center gap-2 rounded-lg px-3 font-semibold text-slate-700 transition-colors duration-200 ease-brand hover:bg-slate-100 hover:text-slate-900 aria-pressed:bg-brand-700 aria-pressed:text-white motion-reduce:transition-none"
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
    <section aria-label={s.medicines.contact} className="flex gap-3 rounded-card border border-info-line bg-info-soft p-4">
      <Info aria-hidden="true" className="mt-0.5 size-5 shrink-0 text-info" />
      <div className="min-w-0 flex-1 space-y-3">
        <p className="text-slate-900">{s.medicines.safety}</p>
        <ul className="flex flex-wrap gap-2">
          {phones.map((p) => (
            <li key={p.phone}>
              <a
                href={`tel:${p.phone}`}
                className="inline-flex min-h-11 items-center gap-2 rounded-lg bg-brand-700 px-4 py-1.5 font-semibold text-white shadow-sm transition-colors duration-200 ease-brand hover:bg-brand-800 motion-reduce:transition-none"
              >
                <Phone aria-hidden="true" className="size-4 shrink-0" />
                <span className="flex flex-col">
                  {s.medicines.contact}
                  {phones.length > 1 && <span className="text-sm font-normal">{p.clinic}</span>}
                </span>
              </a>
            </li>
          ))}
        </ul>
      </div>
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

function EntryItem({ e, s, slot }: Readonly<{ e: Entry; s: PortalStrings; slot?: { slot: Slot; label: string; date: string } }>) {
  const progress = e.days_total !== null ? s.medicines.dayOf(e.day, e.days_total) : e.duration;
  return (
    <li className="flex gap-3 border-t border-line py-3 first:border-t-0 first:pt-0 last:pb-0">
      <span aria-hidden="true" className="mt-0.5 grid size-9 shrink-0 place-items-center rounded-full bg-slate-100 text-slate-700">
        <Pill className="size-4" />
      </span>
      <div className="min-w-0 flex-1 space-y-0.5">
        <LineText e={e} />
        {e.as_written !== null && (
          <p>
            <span className="font-semibold">{s.medicines.asWritten}:</span> {e.as_written}
          </p>
        )}
        <p className="text-sm text-slate-700">
          {progress} · {s.medicines.by(e.doctor_name, e.clinic_name)}
        </p>
        {e.reminder?.enabled === true && (
          <p className="text-sm text-slate-700">{s.medicines.reminderOn(e.reminder.remind_at ?? "")}</p>
        )}
        {slot !== undefined && e.mark !== null && <DoseControl e={e} mark={e.mark} slot={slot} />}
      </div>
    </li>
  );
}

/** A time of day's icon (decorative; the card's title says the time in words). */
const SLOT_ICON: Readonly<Record<Slot, typeof Sun>> = { MORNING: Sunrise, AFTERNOON: Sun, EVENING: Sunset, NIGHT: Moon };

/** A round 44 px stepper button whose name is its words; the arrow is decoration. */
const STEP =
  "inline-flex min-h-11 min-w-11 items-center justify-center gap-1 rounded-full border border-line bg-white px-2 font-medium text-slate-900 shadow-sm transition-colors duration-200 ease-brand hover:border-brand-300 hover:bg-brand-50 disabled:cursor-not-allowed disabled:bg-slate-50 disabled:text-slate-500 disabled:shadow-none motion-reduce:transition-none sm:px-4";

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

  return (
    <div className="space-y-4">
      {!plan.has_prescriptions ? (
        <EmptyState title={s.medicines.empty} icon={<Pill className="size-5" />} />
      ) : (
        <>
          <div className="space-y-2 rounded-card border border-line bg-white p-2 shadow-card">
            <div role="group" aria-label={s.medicines.today} className="flex items-center justify-between gap-2">
              <button type="button" className={STEP} disabled={offset <= -WINDOW_DAYS} onClick={() => setDay(addDays(plan.date, -1))} aria-label={s.medicines.previousDay}>
                <ChevronLeft aria-hidden="true" className="size-5" />
                <span aria-hidden="true" className="hidden sm:inline">
                  {s.medicines.previousDay}
                </span>
              </button>
              <p className="min-w-0 text-center font-semibold text-slate-900" aria-live="polite">
                {offset === 0 && <span className="block text-xs font-semibold uppercase tracking-wide text-brand-700">{s.medicines.today}<span className="sr-only"> · </span></span>}
                {portalCalendarDate(plan.date, s)}
              </p>
              <button type="button" className={STEP} disabled={offset >= WINDOW_DAYS} onClick={() => setDay(addDays(plan.date, 1))} aria-label={s.medicines.nextDay}>
                <span aria-hidden="true" className="hidden sm:inline">
                  {s.medicines.nextDay}
                </span>
                <ChevronRight aria-hidden="true" className="size-5" />
              </button>
            </div>
            {offset !== 0 && (
              <div className="flex justify-center">
                <button type="button" className="inline-flex min-h-11 items-center gap-1.5 rounded-full px-3 font-semibold text-brand-800 hover:bg-brand-50" onClick={() => setDay(undefined)}>
                  {s.medicines.backToToday}
                </button>
              </div>
            )}
          </div>
          {all.length === 0 && <EmptyState title={s.medicines.nothingOn} icon={<CalendarDays className="size-5" />} />}
          {plan.slots.map((slot) => {
            const Icon = SLOT_ICON[slot.slot];
            return (
              <PortalCard key={slot.slot} id={`slot-${slot.slot}`} title={`${slot.label} · ${slot.time}`} icon={<Icon />}>
                <ul>
                  {slot.entries.map((e) => (
                    <EntryItem key={`${e.prescription_id}-${e.item_id}`} e={e} s={s} slot={{ slot: slot.slot, label: slot.label, date: plan.date }} />
                  ))}
                </ul>
              </PortalCard>
            );
          })}
          {plan.as_written.length > 0 && (
            <PortalCard id="as-written" title={s.medicines.asWritten} icon={<Pill />}>
              <ul>
                {plan.as_written.map((e) => (
                  <EntryItem key={`${e.prescription_id}-${e.item_id}`} e={e} s={s} />
                ))}
              </ul>
            </PortalCard>
          )}
        </>
      )}
      {plan.has_prescriptions && (
        <p className="text-sm text-slate-700">{s.medicines.doses.private}</p>
      )}
      <Safety phones={phonesOf(all)} />
    </div>
  );
}

/** The state in words, with the time marked on the clinic's clock (R45, R47). */
export function markText(mark: { status: string; marked_at: string | null }, zone: string, s: PortalStrings): string {
  const d = s.medicines.doses;
  const at = mark.marked_at === null ? "" : portalTime(mark.marked_at, zone, s);
  switch (mark.status) {
    case "TAKEN":
      return at === "" ? d.taken : d.takenAt(at);
    case "SKIPPED":
      return at === "" ? d.skipped : d.skippedAt(at);
    case "NOT_RECORDED":
      return d.notRecorded;
    default:
      return d.upcoming;
  }
}

/**
 * R45-R48: Taken / Skipped within the window, *Change* once marked; for Skipped and Not recorded
 * only "contact your clinic" with the call. Nothing else is ever said about a dose.
 */
function DoseControl({ e, mark: initial, slot }: Readonly<{ e: Entry; mark: Mark; slot: { slot: Slot; label: string; date: string } }>) {
  const { s, leave } = usePortal();
  const d = s.medicines.doses;
  const [mark, setMark] = useState<Mark>(initial);
  const [changing, setChanging] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<unknown>(null);
  const choice = { prescription_id: e.prescription_id, item_id: e.item_id, on_date: slot.date, slot: slot.slot };

  async function send(state: "TAKEN" | "SKIPPED" | null) {
    if (busy) return;
    setBusy(true);
    setError(null);
    try {
      const { data } =
        state === null
          ? await portalDelete("/api/v1/portal/medicine-plan/doses", { query: choice })
          : await portalPut("/api/v1/portal/medicine-plan/doses", { ...choice, state });
      setMark(data);
      setChanging(false);
    } catch (failure) {
      if (!leave(failure)) setError(failure);
    } finally {
      setBusy(false);
    }
  }

  const marked = mark.status === "TAKEN" || mark.status === "SKIPPED";
  const showButtons = mark.markable && (!marked || changing);
  const errorText = portalErrorText(error, s);
  return (
    <div className="mt-2 space-y-2">
      <p aria-live="polite">
        <StatusBadge tone={MARK_TONE[mark.status] ?? "neutral"}>{markText(mark, e.timezone, s)}</StatusBadge>
      </p>
      {showButtons && (
        <div className="grid grid-cols-2 gap-2 min-[400px]:flex min-[400px]:flex-wrap">
          <Button
            variant="primary"
            disabled={busy}
            aria-label={d.markAs(d.taken, e.medicine_name, slot.label)}
            onClick={() => void send("TAKEN")}
            className="min-h-11"
          >
            {d.taken}
          </Button>
          <Button
            disabled={busy}
            aria-label={d.markAs(d.skipped, e.medicine_name, slot.label)}
            onClick={() => void send("SKIPPED")}
            className="min-h-11"
          >
            {d.skipped}
          </Button>
          {marked && (
            <Button variant="ghost" disabled={busy} onClick={() => void send(null)} className="col-span-2 min-h-11">
              {d.clear}
            </Button>
          )}
        </div>
      )}
      {marked && mark.markable && !changing && (
        <button type="button" onClick={() => setChanging(true)} className="inline-flex min-h-11 items-center gap-1.5 font-semibold text-brand-800 underline-offset-4 hover:underline">
          {d.change}
        </button>
      )}
      {(mark.status === "SKIPPED" || mark.status === "NOT_RECORDED") && (
        <p className="text-sm text-slate-800">
          {d.unsure}{" "}
          {e.clinic_phone_e164 !== null && (
            <a href={`tel:${e.clinic_phone_e164}`} className="font-semibold text-brand-800 underline">
              {s.medicines.contact}
            </a>
          )}
        </p>
      )}
      {error !== null && <ErrorNotice error={error} {...(errorText === undefined ? {} : { message: errorText })} />}
    </div>
  );
}

/** A dose's state as a tone; the words say it, the colour only repeats it (never a score, R49). */
const MARK_TONE: Readonly<Record<string, Tone>> = { TAKEN: "done", SKIPPED: "neutral", NOT_RECORDED: "waiting", UPCOMING: "brand" };

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
      <p role="status" className="min-h-6 text-sm font-medium text-success">
        {status}
      </p>
      {courses.length === 0 && <EmptyState title={s.medicines.noCourses} icon={<Pill className="size-5" />} />}
      {courses.length > 0 && <p className="text-sm text-slate-700">{s.medicines.remindersLater}</p>}
      {courses.map((c) => (
        <PortalCard key={c.prescription_id} id={`course-${c.prescription_id}`} title={s.medicines.by(c.doctor_name, c.clinic_name)} icon={<Pill />}>
          <p className="text-sm text-slate-700">
            {s.medicines.from(portalCalendarDate(c.starts_on, s))}
            {c.ends_on !== null && ` · ${s.medicines.until(portalCalendarDate(c.ends_on, s))}`}
          </p>
          {c.revised && !c.reminders_set && (
            <p role="note" className="rounded-lg border border-warning-line bg-warning-soft p-3 font-medium text-slate-900">
              {s.medicines.updated}
            </p>
          )}
          <HistoryToggle prescriptionId={c.prescription_id} />
          <ul>
            {c.lines.map((line) => (
              <li key={line.item_id} className="space-y-2 border-t border-line py-3 first:border-t-0 first:pt-0 last:pb-0">
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
    <div className="space-y-1 rounded-lg border border-line bg-slate-50 px-3 py-1.5">
      <label className="flex min-h-11 cursor-pointer items-center gap-3 font-medium text-slate-900">
        <input
          type="checkbox"
          className="size-5 shrink-0 accent-brand-700"
          checked={reminder.enabled}
          disabled={busy}
          onChange={(e) => void save({ enabled: e.target.checked, remind_at: chosen(time) })}
        />
        {s.medicines.remindMe(slot.label, slot.time)}
      </label>
      {reminder.enabled && (
        <div className="flex flex-wrap items-center gap-2 pb-1.5 pl-8">
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
            className={`${INPUT_BASE} w-auto`}
          />
          {(reminder.remind_at ?? slot.time) !== time && time !== "" && (
            <button
              type="button"
              disabled={busy}
              onClick={() => void save({ enabled: true, remind_at: chosen(time) })}
              className={`${buttonClasses("secondary", "md")} min-h-11`}
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

/** R47, R49: a version's doses by day; counts per state, never a score. */
function HistoryToggle({ prescriptionId }: Readonly<{ prescriptionId: string }>) {
  const { s } = usePortal();
  const [open, setOpen] = useState(false);
  return (
    <div>
      <button type="button" aria-expanded={open} onClick={() => setOpen((o) => !o)} className="inline-flex min-h-11 items-center gap-1.5 font-semibold text-brand-800 underline-offset-4 hover:underline">
        {open ? s.medicines.doses.hideHistory : s.medicines.doses.history}
      </button>
      {open && <HistoryPanel prescriptionId={prescriptionId} />}
    </div>
  );
}

function HistoryPanel({ prescriptionId: first }: Readonly<{ prescriptionId: string }>) {
  const { s } = usePortal();
  const d = s.medicines.doses;
  const [prescriptionId, setPrescriptionId] = useState(first);
  const load = useCallback(
    async (): Promise<History> => (await portalGet("/api/v1/portal/medicine-plan/history", { query: { prescription_id: prescriptionId } })).data,
    [prescriptionId],
  );
  const loaded = usePortalLoad(load);
  if (loaded.status === "loading") return <ScreenLoading label={s.loading} />;
  if (loaded.status === "failed") return <ErrorNotice error={loaded.error} onRetry={loaded.retry} />;
  const h = loaded.data;
  const words: Readonly<Record<string, string>> = { MORNING: s.account.slots.morning, AFTERNOON: s.account.slots.afternoon, EVENING: s.account.slots.evening, NIGHT: s.account.slots.night };
  return (
    <section aria-label={d.historyHeading(h.version)} className="mt-2 space-y-3 rounded-lg border border-line bg-slate-50 p-3">
      <h3 className="font-semibold">{d.historyHeading(h.version)}</h3>
      {h.versions.length > 1 && (
        <div className="flex flex-wrap gap-2">
          {h.versions.map((v) => (
            <button
              key={v.prescription_id}
              type="button"
              aria-pressed={v.prescription_id === h.prescription_id}
              onClick={() => setPrescriptionId(v.prescription_id)}
              className="min-h-11 rounded-lg border border-line bg-white px-3 font-medium text-slate-800 hover:border-brand-300 aria-pressed:border-brand-700 aria-pressed:bg-brand-700 aria-pressed:text-white"
            >
              {d.historyHeading(v.version)}
            </button>
          ))}
        </div>
      )}
      <p className="text-sm font-medium text-slate-900">{d.counts(h.counts["TAKEN"] ?? 0, h.counts["SKIPPED"] ?? 0, h.counts["NOT_RECORDED"] ?? 0)}</p>
      <ul className="space-y-2">
        {h.days.map((day) => (
          <li key={day.date}>
            <p className="text-sm font-semibold">{portalCalendarDate(day.date, s)}</p>
            <ul className="mt-1 space-y-0.5 border-l-2 border-line pl-3 text-sm text-slate-800">
              {day.doses.map((x) => (
                <li key={`${x.item_id}-${x.slot}`}>
                  {words[x.slot]} · {x.medicine_name}
                  {x.dose !== null && ` (${x.dose})`}: {markText(x, h.timezone, s)}
                </li>
              ))}
            </ul>
          </li>
        ))}
      </ul>
      {h.counts["NOT_RECORDED"] !== undefined && h.counts["NOT_RECORDED"] + (h.counts["SKIPPED"] ?? 0) > 0 && (
        <p className="text-sm">
          {d.unsure}{" "}
          {h.clinic_phone_e164 !== null && (
            <a href={`tel:${h.clinic_phone_e164}`} className="font-semibold text-brand-800 underline">
              {s.medicines.contact}
            </a>
          )}
        </p>
      )}
    </section>
  );
}