"use client";

import { useEffect, useState, type FormEvent } from "react";

import { Button } from "@/components/ui/Button";
import { SelectField, TextField } from "@/components/ui/Field";
import { PageHeader } from "@/components/ui/PageHeader";
import { TABLE, TABLE_WRAP, TD, TH, TR } from "@/components/ui/table";
import { ErrorNotice } from "@/features/auth/ErrorNotice";
import { useSession } from "@/features/auth/SessionProvider";
import { formatPaise, parseRupees, rupeesInput } from "@/lib/format/money";

import { KIND_LABELS, KIND_OPTIONS, useFeesApi, type FeeSchedule, type FeeService, type ServiceKind } from "./api";

const PRICE_ERROR = "Enter rupees from 0 to 1,00,000, with at most two decimals, or leave it empty.";

function price(paise: number | null): string {
  return paise === null ? "No price" : formatPaise(paise);
}

/**
 * *Fees* (M6d-P1; FR-BIL-01; spec billing R1-R4): the services the clinic bills for, each with an
 * optional default price, and each doctor's own price where it differs. Everyone who bills may
 * read it; only owners (FEES_MANAGE) change it. A change applies from now on: bills already
 * issued keep their lines (B3). Amounts are typed in rupees and sent as paise.
 */
export function FeeSchedulePage() {
  const api = useFeesApi();
  const { clinic, endSession } = useSession();
  const canManage = clinic.kind === "active" && clinic.membership.permissions.includes("FEES_MANAGE");
  const [schedule, setSchedule] = useState<FeeSchedule | undefined>(undefined);
  const [error, setError] = useState<unknown>(null);
  const [status, setStatus] = useState("");
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    let cancelled = false;
    api.get().then(
      (data) => {
        if (!cancelled) setSchedule(data);
      },
      (failure: unknown) => {
        if (!cancelled && !endSession(failure)) setError(failure);
      },
    );
    return () => {
      cancelled = true;
    };
  }, [api, endSession]);

  async function change(run: () => Promise<FeeSchedule>, done: string): Promise<boolean> {
    setBusy(true);
    setError(null);
    try {
      setSchedule(await run());
      setStatus(done);
      return true;
    } catch (failure) {
      if (!endSession(failure)) setError(failure);
      return false;
    } finally {
      setBusy(false);
    }
  }

  if (schedule === undefined) {
    return error !== null ? <ErrorNotice error={error} /> : <p role="status">Loading the fee schedule…</p>;
  }
  const active = schedule.services.filter((s) => s.active);
  const retired = schedule.services.filter((s) => !s.active);
  const doctorName = new Map(schedule.doctors.map((d) => [d.id, d.display_name]));

  return (
    <section className="max-w-4xl space-y-6">
      <PageHeader title="Fees" description="What the clinic charges, in rupees. A change applies from now on: bills already issued keep their prices." />
      <p role="status" className="min-h-6 font-medium text-emerald-900">
        {status}
      </p>
      {error !== null && <ErrorNotice error={error} />}

      <div className={TABLE_WRAP}>
        <table className={TABLE} role="table">
          <caption className="sr-only">Prices by service and doctor</caption>
          <thead role="rowgroup">
            <tr role="row">
              <th role="columnheader" scope="col" className={TH}>
                Service
              </th>
              <th role="columnheader" scope="col" className={TH}>
                Default price
              </th>
              {schedule.doctors.map((d) => (
                <th key={d.id} role="columnheader" scope="col" className={TH}>
                  {d.display_name}
                </th>
              ))}
            </tr>
          </thead>
          <tbody role="rowgroup">
            {active.map((s) => (
              <tr key={s.id} role="row" className={TR}>
                <td role="cell" data-label="Service" className={TD}>
                  <span className="font-medium">{s.name}</span> <span className="text-sm text-slate-700">({KIND_LABELS[s.kind]})</span>
                </td>
                <td role="cell" data-label="Default price" className={TD}>
                  {price(s.default_price_paise)}
                </td>
                {s.doctor_prices.map((p) => (
                  <td key={p.doctor_id} role="cell" data-label={doctorName.get(p.doctor_id) ?? ""} className={TD}>
                    {price(p.price_paise)}
                    {p.own_price_paise !== null && <span className="text-sm text-slate-700"> (own price)</span>}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      {active.length === 0 && <p>No active services. {canManage ? "Add one below." : "Ask the owner to add them."}</p>}

      {canManage && (
        <>
          <h2 className="text-lg font-semibold">Change a service</h2>
          <ul className="space-y-3">
            {active.map((s) => (
              <li key={s.id}>
                <ServiceCard service={s} schedule={schedule} busy={busy} change={change} api={api} />
              </li>
            ))}
          </ul>
          <AddServiceForm busy={busy} onAdd={(body) => change(() => api.addService(body), `${body.name} added.`)} />
          {retired.length > 0 && (
            <>
              <h2 className="text-lg font-semibold">Retired services</h2>
              <ul className="space-y-2">
                {retired.map((s) => (
                  <li key={s.id} className="flex flex-wrap items-center gap-3 rounded-card border border-slate-200 bg-white p-3">
                    <span>
                      {s.name} <span className="text-sm text-slate-700">({KIND_LABELS[s.kind]})</span>
                    </span>
                    <Button size="sm" disabled={busy} onClick={() => void change(() => api.changeService(s.id, { active: true }), `${s.name} restored.`)}>
                      Restore <span className="sr-only">{s.name}</span>
                    </Button>
                  </li>
                ))}
              </ul>
            </>
          )}
        </>
      )}
    </section>
  );
}

type Change = (run: () => Promise<FeeSchedule>, done: string) => Promise<boolean>;

/** R3-R5: one service's name, kind and default price, its doctors' own prices, and retiring it. */
function ServiceCard({
  service,
  schedule,
  busy,
  change,
  api,
}: Readonly<{ service: FeeService; schedule: FeeSchedule; busy: boolean; change: Change; api: ReturnType<typeof useFeesApi> }>) {
  const [name, setName] = useState(service.name);
  const [kind, setKind] = useState<ServiceKind>(service.kind);
  const [fee, setFee] = useState(rupeesInput(service.default_price_paise));
  const parsed = parseRupees(fee);
  const nameError = name.trim() === "" ? "Enter a name." : undefined;
  const feeError = parsed.ok ? undefined : PRICE_ERROR;

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!parsed.ok || nameError !== undefined) return;
    void change(() => api.changeService(service.id, { name: name.trim(), kind, default_price_paise: parsed.paise }), `${name.trim()} saved.`);
  }

  return (
    <div className="space-y-3 rounded-card border border-slate-200 bg-white p-4">
      <form onSubmit={submit} className="space-y-2" noValidate>
        <h3 className="font-semibold">{service.name}</h3>
        <div className="grid gap-3 sm:grid-cols-3">
          <TextField id={`name-${service.id}`} label="Name" value={name} onChange={setName} maxLength={80} required error={nameError} />
          <SelectField id={`kind-${service.id}`} label="Kind" value={kind} onChange={(v) => setKind(v as ServiceKind)} options={KIND_OPTIONS} />
          <TextField
            id={`price-${service.id}`}
            label="Default price in rupees"
            inputMode="numeric"
            value={fee}
            onChange={setFee}
            hint="Empty for no default price."
            error={feeError}
          />
        </div>
        <div className="flex flex-wrap gap-2">
          <Button type="submit" size="sm" variant="primary" disabled={busy || feeError !== undefined || nameError !== undefined}>
            Save <span className="sr-only">{service.name}</span>
          </Button>
          <Button size="sm" disabled={busy} onClick={() => void change(() => api.changeService(service.id, { active: false }), `${service.name} retired.`)}>
            Retire <span className="sr-only">{service.name}</span>
          </Button>
        </div>
      </form>
      {schedule.doctors.length > 0 && (
        <div className="space-y-2 border-t border-slate-200 pt-3">
          <p className="font-medium">Doctors&apos; own prices</p>
          {service.doctor_prices.map((p) => (
            <DoctorPriceForm
              key={p.doctor_id}
              service={service}
              doctorId={p.doctor_id}
              doctorName={schedule.doctors.find((d) => d.id === p.doctor_id)?.display_name ?? ""}
              own={p.own_price_paise}
              busy={busy}
              change={change}
              api={api}
            />
          ))}
        </div>
      )}
    </div>
  );
}

/** R4: a doctor's own price for one service; empty removes it so the default applies. */
function DoctorPriceForm({
  service,
  doctorId,
  doctorName,
  own,
  busy,
  change,
  api,
}: Readonly<{
  service: FeeService;
  doctorId: string;
  doctorName: string;
  own: number | null;
  busy: boolean;
  change: Change;
  api: ReturnType<typeof useFeesApi>;
}>) {
  const [fee, setFee] = useState(rupeesInput(own));
  const parsed = parseRupees(fee);
  const feeError = parsed.ok ? undefined : PRICE_ERROR;
  const fallback = service.default_price_paise === null ? "no price" : `the default, ${formatPaise(service.default_price_paise)}`;

  function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    if (!parsed.ok) return;
    void change(
      () => api.setDoctorPrice(service.id, doctorId, parsed.paise),
      parsed.paise === null ? `${doctorName} now charges the default for ${service.name}.` : `${doctorName}'s price for ${service.name} saved.`,
    );
  }

  return (
    <form onSubmit={submit} className="flex flex-wrap items-end gap-2" noValidate>
      <div className="min-w-56 flex-1">
        <TextField
          id={`price-${service.id}-${doctorId}`}
          label={`${doctorName}'s price for ${service.name}, in rupees`}
          inputMode="numeric"
          value={fee}
          onChange={setFee}
          hint={`Empty for ${fallback}.`}
          error={feeError}
        />
      </div>
      <Button type="submit" size="sm" disabled={busy || feeError !== undefined}>
        Save <span className="sr-only">{`${doctorName}'s price for ${service.name}`}</span>
      </Button>
    </form>
  );
}

/** R1: a new service goes last unless the owner orders it later. */
function AddServiceForm({
  busy,
  onAdd,
}: Readonly<{ busy: boolean; onAdd: (body: { name: string; kind: ServiceKind; default_price_paise: number | null }) => Promise<boolean> }>) {
  const [name, setName] = useState("");
  const [kind, setKind] = useState<ServiceKind>("PROCEDURE");
  const [fee, setFee] = useState("");
  const [tried, setTried] = useState(false);
  const parsed = parseRupees(fee);
  const nameError = tried && name.trim() === "" ? "Enter a name." : undefined;
  const feeError = parsed.ok ? undefined : PRICE_ERROR;

  async function submit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setTried(true);
    if (!parsed.ok || name.trim() === "") return;
    if (await onAdd({ name: name.trim(), kind, default_price_paise: parsed.paise })) {
      setName("");
      setFee("");
      setTried(false);
    }
  }

  return (
    <form onSubmit={(event) => void submit(event)} className="space-y-2 rounded-card border border-slate-200 bg-white p-4" noValidate>
      <h2 className="text-lg font-semibold">Add a service</h2>
      <div className="grid gap-3 sm:grid-cols-3">
        <TextField id="new-service-name" label="Name" value={name} onChange={setName} maxLength={80} required error={nameError} />
        <SelectField id="new-service-kind" label="Kind" value={kind} onChange={(v) => setKind(v as ServiceKind)} options={KIND_OPTIONS} />
        <TextField
          id="new-service-price"
          label="Default price in rupees"
          inputMode="numeric"
          value={fee}
          onChange={setFee}
          hint="Empty for no default price."
          error={feeError}
        />
      </div>
      <Button type="submit" variant="primary" disabled={busy || feeError !== undefined}>
        Add service
      </Button>
    </form>
  );
}
