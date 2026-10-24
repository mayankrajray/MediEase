"""A patient's dose records on their own request (M6b-P3b; patient portal R54; RUNBOOK).

Until the portal's own data-rights screens exist (FR-PRT-10), support runs these when a patient
asks, after confirming the request came from the account's own email:

- ``export <account-id> --out FILE``: the account's dose records in every clinic as JSON in
  a new file readable by its owner only (IDs, day, slot, state and the time marked; no medicine
  names are stored, so none are written). Never to the terminal: the logs share stdout;
- ``delete <account-id> --confirm``: deletes them, and prints how many.

Nothing else reads dose records across clinics (``SqlAlchemyDoseLifecycle``, a reviewed
exception). The log lines carry the account ID and a count only.

Run: ``docker compose run --rm --no-deps api python -m mediease_api.delivery.cli.dose_data …``.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections.abc import Sequence
from pathlib import Path
from uuid import UUID

import structlog

from mediease_api.bootstrap import build_support_uow
from mediease_api.config.settings import load_settings

logger = structlog.get_logger(__name__)


def main(argv: Sequence[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="dose_data", description=__doc__.splitlines()[0])
    sub = parser.add_subparsers(dest="command", required=True)
    export = sub.add_parser("export", help="print an account's dose records as JSON")
    export.add_argument("account_id", type=UUID)
    export.add_argument("--out", required=True, type=Path, help="a new file for the JSON")
    remove = sub.add_parser("delete", help="delete an account's dose records")
    remove.add_argument("account_id", type=UUID)
    remove.add_argument("--confirm", action="store_true", help="required to delete")
    args = parser.parse_args(argv)

    if args.command == "delete" and not args.confirm:
        print("dose_data: add --confirm to delete; nothing was changed", file=sys.stderr)
        return 2

    uow = build_support_uow(load_settings())
    account: UUID = args.account_id
    with uow:
        if args.command == "export":
            records = uow.dose_lifecycle.export_for_account(account)
            out: Path = args.out
            # A new file, owner-only (health data, R51); refuses to overwrite one.
            fd = os.open(out, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
            with os.fdopen(fd, "w", encoding="utf-8") as handle:
                json.dump(
                    {
                        "account_id": str(account),
                        "dose_records": [
                            {
                                "clinic_id": str(r.clinic_id),
                                "patient_id": str(r.patient_id),
                                "prescription_id": str(r.prescription_id),
                                "item_id": str(r.item_id),
                                "date": r.on_date.isoformat(),
                                "slot": r.slot,
                                "state": r.state,
                                "marked_at": r.marked_at.isoformat(),
                            }
                            for r in records
                        ],
                    },
                    handle,
                    indent=2,
                )
            print(f"dose_data: wrote {len(records)} dose records of {account} to {out}")
            logger.info("support.dose_data_exported", account_id=str(account), count=len(records))
            return 0
        deleted = uow.dose_lifecycle.delete_for_account(account)
        uow.commit()
    print(f"dose_data: deleted {deleted} dose records of {account}")
    logger.info("support.dose_data_deleted", account_id=str(account), count=deleted)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
