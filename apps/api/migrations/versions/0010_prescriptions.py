"""prescriptions and prescription items, immutable once issued (M4-P2)

FR-RX-01..03, 06, 09; spec prescriptions R4-R6, R14; M4-P2 decisions 1A-6A; docs/DATA_MODEL.md
"M4". Expand-only.

One chain of versions per visit (``UNIQUE (visit_id, version)``, at most one draft). AC1 is
enforced here as well as in the application, for every non-superuser role, ours included:

- ``prescriptions``: while a row is a draft anything may change. Once issued, only the
  operational columns may: ``status`` ISSUED -> SUPERSEDED, ``pdf_object_key`` set once (P4),
  ``link_delivery`` from PENDING to SUPERSEDED, SENT or EXPIRED (R14, M5), and ``updated_at``.
  Any other change, and deleting a non-draft, raises ``RX_NOT_DRAFT``.
- ``prescription_items``: inserted, changed or deleted only while their prescription is a draft.
- ``TRUNCATE`` is refused on both.

Revision ID: 0010
Revises: 0009
Create Date: 2026-10-17
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0010"
down_revision: str | None = "0009"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_FREQUENCIES = "'1-0-0', '0-1-0', '0-0-1', '1-0-1', '1-1-1', '1-1-1-1', 'SOS', 'ONCE', 'CUSTOM'"
_TIMINGS = "'BEFORE_FOOD', 'AFTER_FOOD', 'WITH_FOOD', 'EMPTY_STOMACH', 'BEDTIME', 'ANY'"
_DELIVERY = "'PENDING', 'NOT_CONSENTED', 'SUPERSEDED', 'SENT', 'EXPIRED'"
_OPERATIONAL = "ARRAY['status', 'pdf_object_key', 'link_delivery', 'updated_at']"

_PRESCRIPTION_FUNCTION = f"""
CREATE OR REPLACE FUNCTION prescriptions_immutable() RETURNS trigger
LANGUAGE plpgsql AS $$
BEGIN
    IF TG_OP = 'TRUNCATE' THEN
        RAISE EXCEPTION 'RX_NOT_DRAFT: prescriptions cannot be truncated (FR-RX-09)'
            USING ERRCODE = 'restrict_violation';
    END IF;
    IF OLD.status = 'DRAFT' THEN
        RETURN CASE WHEN TG_OP = 'DELETE' THEN OLD ELSE NEW END;
    END IF;
    IF TG_OP = 'DELETE' THEN
        RAISE EXCEPTION 'RX_NOT_DRAFT: an issued prescription cannot be deleted (FR-RX-09)'
            USING ERRCODE = 'restrict_violation';
    END IF;
    IF (to_jsonb(NEW) - {_OPERATIONAL}) IS DISTINCT FROM (to_jsonb(OLD) - {_OPERATIONAL})
       OR NOT (NEW.status = OLD.status OR (OLD.status = 'ISSUED' AND NEW.status = 'SUPERSEDED'))
       OR NOT (NEW.pdf_object_key IS NOT DISTINCT FROM OLD.pdf_object_key
               OR OLD.pdf_object_key IS NULL)
       OR NOT (NEW.link_delivery IS NOT DISTINCT FROM OLD.link_delivery
               OR (OLD.link_delivery = 'PENDING'
                   AND NEW.link_delivery IN ('SUPERSEDED', 'SENT', 'EXPIRED')))
    THEN
        RAISE EXCEPTION 'RX_NOT_DRAFT: an issued prescription is immutable (FR-RX-09)'
            USING ERRCODE = 'restrict_violation';
    END IF;
    RETURN NEW;
END;
$$
"""

_ITEM_FUNCTION = """
CREATE OR REPLACE FUNCTION prescription_items_frozen() RETURNS trigger
LANGUAGE plpgsql AS $$
DECLARE
    parent_status text;
BEGIN
    IF TG_OP = 'TRUNCATE' THEN
        RAISE EXCEPTION 'RX_NOT_DRAFT: prescription items cannot be truncated (FR-RX-09)'
            USING ERRCODE = 'restrict_violation';
    END IF;
    IF TG_OP IN ('UPDATE', 'DELETE') THEN
        SELECT status INTO parent_status FROM prescriptions WHERE id = OLD.prescription_id;
        IF parent_status IS DISTINCT FROM 'DRAFT' THEN
            RAISE EXCEPTION 'RX_NOT_DRAFT: items of an issued prescription are immutable'
                USING ERRCODE = 'restrict_violation';
        END IF;
    END IF;
    IF TG_OP IN ('INSERT', 'UPDATE') THEN
        SELECT status INTO parent_status FROM prescriptions WHERE id = NEW.prescription_id;
        IF parent_status IS DISTINCT FROM 'DRAFT' THEN
            RAISE EXCEPTION 'RX_NOT_DRAFT: items of an issued prescription are immutable'
                USING ERRCODE = 'restrict_violation';
        END IF;
        RETURN NEW;
    END IF;
    RETURN OLD;
END;
$$
"""

_TRIGGERS = (
    """CREATE TRIGGER trg_prescriptions_immutable BEFORE UPDATE OR DELETE ON prescriptions
    FOR EACH ROW EXECUTE FUNCTION prescriptions_immutable()""",
    """CREATE TRIGGER trg_prescriptions_no_truncate BEFORE TRUNCATE ON prescriptions
    FOR EACH STATEMENT EXECUTE FUNCTION prescriptions_immutable()""",
    """CREATE TRIGGER trg_prescription_items_frozen
    BEFORE INSERT OR UPDATE OR DELETE ON prescription_items
    FOR EACH ROW EXECUTE FUNCTION prescription_items_frozen()""",
    """CREATE TRIGGER trg_prescription_items_no_truncate BEFORE TRUNCATE ON prescription_items
    FOR EACH STATEMENT EXECUTE FUNCTION prescription_items_frozen()""",
)


def _length(table: str, column: str, limit: int, *, required: bool = False) -> sa.CheckConstraint:
    rule = (
        f"char_length({column}) BETWEEN 1 AND {limit}"
        if required
        else f"{column} IS NULL OR char_length({column}) <= {limit}"
    )
    return sa.CheckConstraint(rule, name=op.f(f"ck_{table}_{column}_length"))


def upgrade() -> None:
    op.create_table(
        "prescriptions",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("clinic_id", sa.Uuid(), nullable=False),
        sa.Column("visit_id", sa.Uuid(), nullable=False),
        sa.Column("patient_id", sa.Uuid(), nullable=False),
        sa.Column("doctor_id", sa.Uuid(), nullable=False),
        sa.Column("version", sa.SmallInteger(), nullable=False),
        sa.Column("supersedes_id", sa.Uuid(), nullable=True),
        sa.Column("status", sa.Text(), nullable=False),
        sa.Column("revision", sa.Integer(), server_default=sa.text("1"), nullable=False),
        sa.Column(
            "advice",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'{}'::jsonb"),
            nullable=False,
        ),
        sa.Column("follow_up_date", sa.Date(), nullable=True),
        sa.Column("language", sa.Text(), nullable=True),
        sa.Column("issued_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("doctor_snapshot", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("clinic_snapshot", postgresql.JSONB(astext_type=sa.Text()), nullable=True),
        sa.Column("pdf_object_key", sa.Text(), nullable=True),
        sa.Column("link_delivery", sa.Text(), nullable=True),
        sa.Column("link_delivery_requested_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by", sa.Uuid(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.CheckConstraint(
            "status IN ('DRAFT', 'ISSUED', 'SUPERSEDED')", name=op.f("ck_prescriptions_status")
        ),
        sa.CheckConstraint("language IN ('en', 'hi')", name=op.f("ck_prescriptions_language")),
        sa.CheckConstraint(
            f"link_delivery IN ({_DELIVERY})", name=op.f("ck_prescriptions_link_delivery")
        ),
        sa.CheckConstraint("version >= 1", name=op.f("ck_prescriptions_version_positive")),
        sa.CheckConstraint(
            "(version = 1) = (supersedes_id IS NULL)", name=op.f("ck_prescriptions_version_chain")
        ),
        sa.CheckConstraint("revision >= 1", name=op.f("ck_prescriptions_revision_positive")),
        sa.CheckConstraint(
            "status = 'DRAFT' OR (issued_at IS NOT NULL AND language IS NOT NULL"
            " AND doctor_snapshot IS NOT NULL AND clinic_snapshot IS NOT NULL"
            " AND link_delivery IS NOT NULL)",
            name=op.f("ck_prescriptions_issued_is_complete"),
        ),
        sa.CheckConstraint(
            "status <> 'DRAFT' OR (issued_at IS NULL AND link_delivery IS NULL"
            " AND pdf_object_key IS NULL)",
            name=op.f("ck_prescriptions_draft_is_unissued"),
        ),
        sa.ForeignKeyConstraint(
            ["clinic_id"], ["clinics.id"], name=op.f("fk_prescriptions_clinic_id_clinics")
        ),
        sa.ForeignKeyConstraint(
            ["visit_id"], ["visits.id"], name=op.f("fk_prescriptions_visit_id_visits")
        ),
        sa.ForeignKeyConstraint(
            ["patient_id"], ["patients.id"], name=op.f("fk_prescriptions_patient_id_patients")
        ),
        sa.ForeignKeyConstraint(
            ["doctor_id"], ["doctors.id"], name=op.f("fk_prescriptions_doctor_id_doctors")
        ),
        sa.ForeignKeyConstraint(
            ["supersedes_id"],
            ["prescriptions.id"],
            name=op.f("fk_prescriptions_supersedes_id_prescriptions"),
        ),
        sa.ForeignKeyConstraint(
            ["created_by"], ["users.id"], name=op.f("fk_prescriptions_created_by_users")
        ),
        sa.PrimaryKeyConstraint("id", name=op.f("pk_prescriptions")),
        sa.UniqueConstraint("visit_id", "version", name=op.f("uq_prescriptions_visit_id_version")),
    )
    op.create_index(
        "uq_prescriptions_visit_id_draft",
        "prescriptions",
        ["visit_id"],
        unique=True,
        postgresql_where=sa.text("status = 'DRAFT'"),
    )
    op.create_index(
        op.f("ix_prescriptions_clinic_id_patient_id_issued_at"),
        "prescriptions",
        ["clinic_id", "patient_id", sa.text("issued_at DESC")],
    )

    t = "prescription_items"
    op.create_table(
        t,
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("clinic_id", sa.Uuid(), nullable=False),
        sa.Column("prescription_id", sa.Uuid(), nullable=False),
        sa.Column("position", sa.SmallInteger(), nullable=False),
        sa.Column("medicine_name", sa.Text(), nullable=False),
        sa.Column("form", sa.Text(), nullable=True),
        sa.Column("strength", sa.Text(), nullable=True),
        sa.Column("dose", sa.Text(), nullable=True),
        sa.Column("frequency", sa.Text(), nullable=True),
        sa.Column("frequency_text", sa.Text(), nullable=True),
        sa.Column("timing", sa.Text(), nullable=True),
        sa.Column("duration_days", sa.SmallInteger(), nullable=True),
        sa.Column("quantity", sa.Text(), nullable=True),
        sa.Column(
            "preparation",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column(
            "storage",
            postgresql.JSONB(astext_type=sa.Text()),
            server_default=sa.text("'[]'::jsonb"),
            nullable=False,
        ),
        sa.Column("warnings", sa.Text(), nullable=True),
        sa.Column("notes", sa.Text(), nullable=True),
        sa.CheckConstraint(f"frequency IN ({_FREQUENCIES})", name=op.f(f"ck_{t}_frequency")),
        sa.CheckConstraint(f"timing IN ({_TIMINGS})", name=op.f(f"ck_{t}_timing")),
        sa.CheckConstraint("position >= 1", name=op.f(f"ck_{t}_position_positive")),
        sa.CheckConstraint(
            "(frequency IS NOT DISTINCT FROM 'CUSTOM') = (frequency_text IS NOT NULL)",
            name=op.f(f"ck_{t}_custom_frequency_text"),
        ),
        sa.CheckConstraint(
            "duration_days IS NULL OR duration_days BETWEEN 1 AND 365",
            name=op.f(f"ck_{t}_duration_days_range"),
        ),
        _length(t, "medicine_name", 200, required=True),
        _length(t, "form", 100),
        _length(t, "strength", 100),
        _length(t, "dose", 100),
        _length(t, "frequency_text", 100),
        _length(t, "quantity", 100),
        _length(t, "warnings", 500),
        _length(t, "notes", 1000),
        sa.ForeignKeyConstraint(
            ["clinic_id"], ["clinics.id"], name=op.f(f"fk_{t}_clinic_id_clinics")
        ),
        sa.ForeignKeyConstraint(
            ["prescription_id"],
            ["prescriptions.id"],
            name=op.f(f"fk_{t}_prescription_id_prescriptions"),
        ),
        sa.PrimaryKeyConstraint("id", name=op.f(f"pk_{t}")),
        sa.UniqueConstraint(
            "prescription_id", "position", name=op.f(f"uq_{t}_prescription_id_position")
        ),
    )
    op.execute(_PRESCRIPTION_FUNCTION)
    op.execute(_ITEM_FUNCTION)
    for trigger in _TRIGGERS:
        op.execute(trigger)


def downgrade() -> None:
    op.drop_table("prescription_items")
    op.drop_table("prescriptions")
    op.execute("DROP FUNCTION IF EXISTS prescription_items_frozen()")
    op.execute("DROP FUNCTION IF EXISTS prescriptions_immutable()")
