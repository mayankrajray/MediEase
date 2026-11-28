"""Answer a patient data request: export one patient's record, or erase them (M9-P3; RUNBOOK §43).

Only on the clinic owner's **written** request (the clinic is the Data Fiduciary; RUNBOOK §12).

    python -m mediease_api.delivery.cli.patient_data export <clinic-slug> <patient-code>
    python -m mediease_api.delivery.cli.patient_data erase  <clinic-slug> <patient-code>

``export`` writes ``/exports/<slug>-<code>-<date>.zip``, an AES-256 encrypted zip with
``record.json`` and the stored prescription PDFs and reports, as a new owner-only file. Its
password is printed **once**: give it to the clinic by another channel than the file (a phone
call), never in the same email. ``erase`` shows what it would change, then asks for the patient's
code to be typed again (``--confirm <code>`` instead, for a script); it is refused while the
patient has an upcoming appointment or an open booking request. Both are audited on the clinic's
log. Nothing about the patient is logged or printed but the code and counts.

Exit codes: 0 done; 1 refused (the reason is printed); 2 a usage problem or not confirmed.
"""

from __future__ import annotations

import argparse
import os
import secrets
import sys
from collections.abc import Callable, Sequence
from datetime import UTC, datetime
from pathlib import Path

import pyzipper

from mediease_api.application.patients.data_requests import DataRequestRefused, PatientExport
from mediease_api.bootstrap import build_patient_data_requests
from mediease_api.config.settings import load_settings

EXPORT_DIR = Path("/exports")
README = (
    "MediEase patient data export\n\n"
    "record.json holds every row MediEase stores about this patient for this clinic, by table.\n"
    "prescriptions/ holds the issued prescriptions as printed; reports/ the reports attached to\n"
    "visits. Open with 7-Zip or WinRAR (AES-256); Windows' own Explorer cannot.\n"
)


def write_archive(export: PatientExport, out: Path, password: str) -> None:
    """A new owner-only file (it refuses to overwrite one), AES-256 encrypted."""
    fd = os.open(out, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with (
        os.fdopen(fd, "wb") as handle,
        pyzipper.AESZipFile(
            handle, "w", compression=pyzipper.ZIP_DEFLATED, encryption=pyzipper.WZ_AES
        ) as archive,
    ):
        archive.setpassword(password.encode())
        archive.setencryption(pyzipper.WZ_AES, nbits=256)
        archive.writestr("README.txt", README)
        archive.writestr("record.json", export.record_json)
        for name, data in sorted(export.files.items()):
            archive.writestr(name, data)


def main(
    argv: Sequence[str] | None = None,
    *,
    ask: Callable[[str], str] = input,
    out_dir: Path = EXPORT_DIR,
) -> int:
    parser = argparse.ArgumentParser(
        prog="patient_data", description=(__doc__ or "").splitlines()[0]
    )
    sub = parser.add_subparsers(dest="command", required=True)
    for name, text in (("export", "write the patient's record"), ("erase", "anonymise them")):
        command = sub.add_parser(name, help=text)
        command.add_argument("clinic_slug")
        command.add_argument("patient_code")
        if name == "erase":
            command.add_argument("--confirm", metavar="CODE", help="the patient's code, to go on")
    args = parser.parse_args(argv)

    requests = build_patient_data_requests(load_settings())
    try:
        if args.command == "export":
            return _export(requests.export.execute(args.clinic_slug, args.patient_code), out_dir)
        ref, blockers = requests.erase.check(args.clinic_slug, args.patient_code)
        if ref.already_erased:
            raise DataRequestRefused("already_erased", "this patient has already been erased")
        if blockers.any:
            print(
                f"patient_data: {ref.code} has {blockers.upcoming_appointments} upcoming "
                f"appointment(s) and {blockers.open_booking_requests} open booking request(s); "
                "the clinic must cancel or answer them first. Nothing was changed.",
                file=sys.stderr,
            )
            return 1
        print(
            f"patient_data: erasing {ref.code} of {ref.clinic_slug} removes the name, phone, date "
            "of birth (the age stays), guardian and consents; their app links, reminder choices, "
            "dose marks and open links; scheduled reminders; the phone on messages and booking "
            "requests; and the stored PDFs that printed them. Visits, prescriptions, bills and "
            "reports stay with the clinic under the code. This cannot be undone."
        )
        typed = args.confirm or ask(f"Type the patient's code ({ref.code}) to erase them: ")
        if typed.strip().upper() != ref.code:
            print("patient_data: not confirmed; nothing was changed", file=sys.stderr)
            return 2
        outcome = requests.erase.execute(args.clinic_slug, args.patient_code)
    except DataRequestRefused as refused:
        print(f"patient_data: {refused.reason}; nothing was changed", file=sys.stderr)
        return 1
    changed = ", ".join(f"{k.replace('_', ' ')} {v}" for k, v in outcome.counts.items() if v)
    print(f"patient_data: erased {outcome.ref.code} ({changed}; {outcome.pdfs_removed} PDF files)")
    print("patient_data: recorded in the clinic's audit log as patient.erased")
    return 0


def _export(export: PatientExport, out_dir: Path) -> int:
    day = datetime.now(UTC).strftime("%Y%m%d")
    out = out_dir / f"{export.ref.clinic_slug}-{export.ref.code.lower()}-{day}.zip"
    password = secrets.token_urlsafe(18)
    try:
        write_archive(export, out, password)
    except FileExistsError:
        print(f"patient_data: {out.name} already exists; move it away first", file=sys.stderr)
        return 2
    print(f"patient_data: wrote {out.name} ({len(export.files)} files, record.json)")
    if export.missing:
        print(f"patient_data: {len(export.missing)} recorded file(s) were not in storage")
    print(f"patient_data: password (shown once; give it by phone, not with the file): {password}")
    print("patient_data: recorded in the clinic's audit log as patient.data_exported")
    return 0


if __name__ == "__main__":
    sys.exit(main())
