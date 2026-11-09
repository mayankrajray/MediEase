"use client";

import { CalendarDays, Plus, Search, Users } from "lucide-react";
import { useState, type ReactNode } from "react";

import { ConfirmDialog } from "@/components/ConfirmDialog";
import { Dialog } from "@/components/Dialog";
import { Drawer } from "@/components/Drawer";
import { Menu } from "@/components/Menu";
import { Alert } from "@/components/ui/Alert";
import { Avatar } from "@/components/ui/Avatar";
import { Breadcrumbs } from "@/components/ui/Breadcrumbs";
import { Button, type ButtonVariant } from "@/components/ui/Button";
import { Card } from "@/components/ui/Card";
import { EmptyState } from "@/components/ui/EmptyState";
import {
  CheckboxField,
  DateField,
  ErrorSummary,
  SelectField,
  TextAreaField,
  TextField,
  TimeField,
} from "@/components/ui/Field";
import { KeyValue } from "@/components/ui/KeyValue";
import { Emblem, Logo } from "@/components/ui/Logo";
import { PageHeader } from "@/components/ui/PageHeader";
import { Pagination } from "@/components/ui/Pagination";
import { Skeleton } from "@/components/ui/Skeleton";
import { StatusBadge, type Tone } from "@/components/ui/StatusBadge";
import { TABLE, TABLE_WRAP, TD, TH, TR } from "@/components/ui/table";
import { Tabs } from "@/components/ui/Tabs";
import { ToastProvider, useToast } from "@/components/ui/Toast";
import { Tooltip } from "@/components/ui/Tooltip";
import { ErrorNotice } from "@/features/auth/ErrorNotice";
import { ApiError } from "@/lib/api/client";

/**
 * The design system in one place (M7c-P7; DESIGN.md): every shared component in its states, on
 * synthetic data only. Reviewed by eye at 1366 and 360 px and checked by axe in
 * e2e/design-system.spec.ts. It reads no API and shows no real person.
 */
const SWATCHES: readonly { readonly name: string; readonly className: string; readonly value: string }[] = [
  { name: "Primary", className: "bg-brand-700", value: "#147D72" },
  { name: "Primary soft", className: "bg-brand-100", value: "#DDF3EE" },
  { name: "Background", className: "bg-canvas", value: "#F5F9F8" },
  { name: "Surface", className: "bg-surface", value: "#FFFFFF" },
  { name: "Text", className: "bg-ink", value: "#172B35" },
  { name: "Border", className: "bg-line", value: "#E8EEF1" },
  { name: "Attention", className: "bg-attention", value: "#E8A23A" },
  { name: "Success", className: "bg-success", value: "#166534" },
  { name: "Error", className: "bg-danger", value: "#B42318" },
  { name: "Info", className: "bg-info", value: "#1F5FAD" },
];

const TONES: readonly Tone[] = ["neutral", "brand", "waiting", "active", "done", "missed", "danger"];
const VARIANTS: readonly ButtonVariant[] = ["primary", "secondary", "ghost", "danger"];

const FAILED = new ApiError("SAMPLE", "The queue could not be loaded.", 503, "req-sample-01");

function Section({ id, title, children }: { id: string; title: string; children: ReactNode }) {
  return (
    <section aria-labelledby={id} className="space-y-4">
      <h2 id={id} className="heading-6 text-slate-900">
        {title}
      </h2>
      {children}
    </section>
  );
}

function ToastDemo() {
  const toast = useToast();
  return (
    <Button onClick={() => toast({ title: "Appointment booked", description: "Asha Rao, Tue 11 Nov, 10:30 AM" })}>
      Show a toast
    </Button>
  );
}

export function Showcase() {
  const [name, setName] = useState("Asha Rao");
  const [phone, setPhone] = useState("98765");
  const [day, setDay] = useState("2026-11-11");
  const [time, setTime] = useState("10:30");
  const [reason, setReason] = useState("FOLLOW_UP");
  const [note, setNote] = useState("");
  const [consent, setConsent] = useState(true);
  const [open, setOpen] = useState<"dialog" | "drawer" | "confirm" | null>(null);
  const [page, setPage] = useState(2);
  const phoneError = phone.length < 10 ? "Enter a 10-digit mobile number." : undefined;

  return (
    <ToastProvider>
      <div className="min-h-screen bg-canvas">
        <header className="border-b border-line bg-surface">
          <div className="mx-auto flex max-w-6xl items-center justify-between gap-3 px-4 py-3">
            <Logo />
            <StatusBadge tone="brand">Design system</StatusBadge>
          </div>
        </header>
        <main id="main" className="mx-auto max-w-6xl space-y-12 px-4 py-8">
          <PageHeader
            breadcrumbs={<Breadcrumbs items={[{ label: "MediEase", href: "/" }, { label: "Design system" }]} />}
            title="Design system"
            description="The shared tokens and components every MediEase screen is built from. Sample data only."
            actions={
              <>
                <Button icon={<Search className="size-4" />}>Search</Button>
                <Button variant="primary" icon={<Plus className="size-4" />}>
                  Add a patient
                </Button>
              </>
            }
          />

          <Section id="ds-colour" title="Colour">
            <ul className="grid grid-cols-2 gap-3 sm:grid-cols-5">
              {SWATCHES.map((s) => (
                <li key={s.name} className="overflow-hidden rounded-card border border-line bg-surface">
                  <div aria-hidden="true" className={`h-14 ${s.className}`} />
                  <div className="p-3">
                    <p className="text-sm font-semibold">{s.name}</p>
                    <p className="font-mono text-xs text-slate-700">{s.value}</p>
                  </div>
                </li>
              ))}
            </ul>
          </Section>

          <Section id="ds-type" title="Typography">
            <Card>
              <div className="space-y-3">
                <p className="heading-3">Your clinic&apos;s day, in one place</p>
                <p className="heading-5">Today&apos;s queue</p>
                <p className="heading-6">Next appointments</p>
                <p className="title-3">Dr. Meera Iyer, General physician</p>
                <p className="body-3 max-w-prose text-slate-800">
                  Body text is Manrope at 16 px for forms and patient pages, and 14 px in dense clinic tables.
                </p>
                <p className="caption-2 text-slate-700">Caption: last updated 2 minutes ago</p>
                <p lang="hi" className="body-3">
                  हिंदी पाठ फ़ोन के अपने देवनागरी फ़ॉन्ट में दिखता है।
                </p>
              </div>
            </Card>
          </Section>

          <Section id="ds-brand" title="Logo">
            <div className="flex flex-wrap items-center gap-6">
              <Logo size="lg" />
              <Logo size="md" />
              <Logo />
              <span className="inline-flex rounded-card bg-slate-900 p-3">
                <Logo tone="onDark" />
              </span>
              <Emblem className="size-10" />
            </div>
          </Section>

          <Section id="ds-buttons" title="Buttons">
            <div className="space-y-3">
              {VARIANTS.map((variant) => (
                <div key={variant} className="flex flex-wrap items-center gap-3">
                  <Button variant={variant} size="sm">
                    Small {variant}
                  </Button>
                  <Button variant={variant}>Medium {variant}</Button>
                  <Button variant={variant} size="lg">
                    Large {variant}
                  </Button>
                  <Button variant={variant} loading>
                    Saving
                  </Button>
                  <Button variant={variant} disabled>
                    Disabled {variant}
                  </Button>
                </div>
              ))}
            </div>
          </Section>

          <Section id="ds-forms" title="Forms">
            <Card title="New appointment" description="Fields show their hint, their error and (required) in words.">
              <div className="space-y-4">
                <ErrorSummary errors={phoneError === undefined ? [] : [{ id: "ds-phone", message: phoneError }]} />
                <div className="grid gap-4 sm:grid-cols-2">
                  <TextField id="ds-name" label="Patient name" value={name} onChange={setName} required />
                  <TextField
                    id="ds-phone"
                    label="Mobile number"
                    value={phone}
                    onChange={setPhone}
                    hint="10 digits, without +91"
                    error={phoneError}
                    inputMode="tel"
                    required
                  />
                  <DateField id="ds-day" label="Date" value={day} onChange={setDay} />
                  <TimeField id="ds-time" label="Time" value={time} onChange={setTime} />
                  <SelectField
                    id="ds-reason"
                    label="Reason"
                    value={reason}
                    onChange={setReason}
                    options={[
                      { value: "FOLLOW_UP", label: "Follow-up" },
                      { value: "NEW", label: "New problem" },
                    ]}
                  />
                  <TextField id="ds-disabled" label="Clinic" value="Sample Clinic" onChange={() => undefined} hint="Set by your sign-in" />
                </div>
                <TextAreaField id="ds-note" label="Note for the doctor" value={note} onChange={setNote} maxLength={200} />
                <CheckboxField id="ds-consent" label="Send reminders on WhatsApp" checked={consent} onChange={setConsent} />
                <div className="flex flex-wrap justify-end gap-2">
                  <Button>Cancel</Button>
                  <Button variant="primary" type="submit">
                    Book appointment
                  </Button>
                </div>
              </div>
            </Card>
          </Section>

          <Section id="ds-status" title="Status and messages">
            <div className="flex flex-wrap gap-2">
              {TONES.map((tone) => (
                <StatusBadge key={tone} tone={tone}>
                  {tone[0]?.toUpperCase()}
                  {tone.slice(1)}
                </StatusBadge>
              ))}
            </div>
            <div className="grid gap-3 md:grid-cols-2">
              <Alert tone="info" title="Reminders go out at 9:00 AM">
                Patients who said no to WhatsApp are not messaged.
              </Alert>
              <Alert tone="success" title="Prescription sent">
                Asha Rao received the link on WhatsApp.
              </Alert>
              <Alert tone="warning" title="Two bookings to move">
                Dr. Iyer is on leave on Thursday.
              </Alert>
              <Alert tone="danger" title="The bill could not be saved">
                Check the amount and try again.
              </Alert>
            </div>
            <ErrorNotice error={FAILED} onRetry={() => undefined} />
            <ToastDemo />
          </Section>

          <Section id="ds-data" title="Cards, tables and details">
            <div className="grid gap-4 lg:grid-cols-3">
              <Card title="Patient" action={<Tooltip content="Opens the patient's record"><Button size="sm">Open</Button></Tooltip>}>
                <div className="mb-4 flex items-center gap-3">
                  <Avatar name="Asha Rao" />
                  <div>
                    <p className="font-semibold">Asha Rao</p>
                    <p className="text-sm text-slate-700">SC-0142 · 34 years</p>
                  </div>
                </div>
                <KeyValue
                  items={[
                    { label: "Mobile", value: "•••••• 4321" },
                    { label: "Last visit", value: "28 Oct 2026" },
                    { label: "Language", value: "Hindi" },
                    { label: "Allergies", value: null },
                  ]}
                />
              </Card>
              <div className={`lg:col-span-2 ${TABLE_WRAP}`}>
                <table className={TABLE} role="table">
                  <thead role="rowgroup">
                    <tr role="row">
                      <th role="columnheader" className={TH}>
                        Token
                      </th>
                      <th role="columnheader" className={TH}>
                        Patient
                      </th>
                      <th role="columnheader" className={TH}>
                        Status
                      </th>
                    </tr>
                  </thead>
                  <tbody role="rowgroup">
                    {[
                      { token: 7, patient: "Ravi Kumar", status: "Waiting", tone: "waiting" as const },
                      { token: 8, patient: "Meena Joshi", status: "In consultation", tone: "active" as const },
                      { token: 9, patient: "Imran Shaikh", status: "Done", tone: "done" as const },
                    ].map((r) => (
                      <tr key={r.token} role="row" className={TR}>
                        <td role="cell" data-label="Token" className={TD}>
                          #{r.token}
                        </td>
                        <td role="cell" data-label="Patient" className={TD}>
                          {r.patient}
                        </td>
                        <td role="cell" data-label="Status" className={TD}>
                          <StatusBadge tone={r.tone}>{r.status}</StatusBadge>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </div>
            <Pagination page={page} total={7} onPage={setPage} label="Patient list pages" />
          </Section>

          <Section id="ds-nav" title="Navigation and overlays">
            <Tabs
              label="Patient record"
              items={[
                { value: "visits", label: "Visits", content: <p className="pt-3 text-slate-700">Four visits since June.</p> },
                { value: "rx", label: "Prescriptions", content: <p className="pt-3 text-slate-700">Two current prescriptions.</p> },
              ]}
            />
            <div className="flex flex-wrap items-center gap-2">
              <Button onClick={() => setOpen("dialog")}>Open a dialog</Button>
              <Button onClick={() => setOpen("drawer")}>Open a drawer</Button>
              <Button variant="danger" onClick={() => setOpen("confirm")}>
                Cancel appointment
              </Button>
              <Menu
                label="More actions"
                items={[
                  { label: "Copy live link", onSelect: () => undefined },
                  { label: "Print token", onSelect: () => undefined },
                ]}
              />
            </div>
          </Section>

          <Section id="ds-states" title="Loading and empty">
            <div className="grid gap-4 md:grid-cols-2">
              <Card title="Loading">
                <p role="status" className="sr-only">
                  Loading the queue
                </p>
                <div className="space-y-2">
                  <Skeleton className="h-5 w-2/3" />
                  <Skeleton className="h-5 w-1/2" />
                  <Skeleton className="h-5 w-3/4" />
                </div>
              </Card>
              <EmptyState
                icon={<CalendarDays className="size-5" />}
                title="No appointments today"
                action={
                  <Button variant="primary" icon={<Users className="size-4" />}>
                    Add a walk-in
                  </Button>
                }
              >
                Bookings and walk-ins appear here as they arrive.
              </EmptyState>
            </div>
          </Section>
        </main>

        {open === "dialog" && (
          <Dialog title="Reschedule" onClose={() => setOpen(null)}>
            <p className="text-slate-700">Choose a new time for Asha Rao.</p>
            <div className="flex justify-end">
              <Button variant="primary" onClick={() => setOpen(null)}>
                Done
              </Button>
            </div>
          </Dialog>
        )}
        {open === "drawer" && (
          <Drawer title="Book an appointment" onClose={() => setOpen(null)}>
            <p className="text-slate-700">The booking drawer keeps the patient search focused.</p>
          </Drawer>
        )}
        {open === "confirm" && (
          <ConfirmDialog
            title="Cancel this appointment?"
            confirmLabel="Cancel appointment"
            danger
            onConfirm={() => setOpen(null)}
            onClose={() => setOpen(null)}
          >
            Asha Rao will get a WhatsApp message that it was cancelled.
          </ConfirmDialog>
        )}
      </div>
    </ToastProvider>
  );
}
