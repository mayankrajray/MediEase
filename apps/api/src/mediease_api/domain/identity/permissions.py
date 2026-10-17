"""The permission matrix (PRD §8.1, normative; spec §2).

One ``Permission`` per P0 action; each role maps to the set it may perform.
Endpoints declare the permission they need; they never test roles directly, so
changing who may do what is a change to this table and its test.

Platform ops are not a role: ops routes require ``is_platform_ops`` and clinic
routes refuse ops users (spec R10).
"""

from __future__ import annotations

from enum import StrEnum

from mediease_api.domain.identity.membership import Role


class Permission(StrEnum):
    CLINIC_VIEW = "CLINIC_VIEW"
    DOCTORS_VIEW = "DOCTORS_VIEW"
    CLINIC_MANAGE = "CLINIC_MANAGE"
    STAFF_MANAGE = "STAFF_MANAGE"
    PATIENTS_MANAGE = "PATIENTS_MANAGE"
    APPOINTMENTS_MANAGE = "APPOINTMENTS_MANAGE"
    # M3 (spec appointments D5): weekly schedules, leave and extra sessions. Ops set schedules
    # during onboarding through their own route, not through this permission.
    SCHEDULES_MANAGE = "SCHEDULES_MANAGE"
    QUEUE_MOVE = "QUEUE_MOVE"
    REMINDERS_SCHEDULE = "REMINDERS_SCHEDULE"
    CLINICAL_VIEW = "CLINICAL_VIEW"
    CLINICAL_WRITE = "CLINICAL_WRITE"
    # M4-P4 (spec prescriptions D6): print an issued prescription. Every role, front desk too,
    # without seeing its content on screen; only the latest version unless CLINICAL_VIEW (1A).
    RX_PRINT = "RX_PRINT"
    USAGE_METRICS_VIEW = "USAGE_METRICS_VIEW"


_EVERY_ROLE = frozenset(
    {
        Permission.CLINIC_VIEW,
        Permission.DOCTORS_VIEW,
        Permission.PATIENTS_MANAGE,
        Permission.APPOINTMENTS_MANAGE,
        Permission.QUEUE_MOVE,
        Permission.REMINDERS_SCHEDULE,
        Permission.RX_PRINT,
    }
)

ROLE_PERMISSIONS: dict[Role, frozenset[Permission]] = {
    Role.OWNER: _EVERY_ROLE
    | {
        Permission.CLINIC_MANAGE,
        Permission.STAFF_MANAGE,
        Permission.SCHEDULES_MANAGE,
        Permission.CLINICAL_VIEW,
        Permission.USAGE_METRICS_VIEW,
    },
    Role.DOCTOR: _EVERY_ROLE
    | {Permission.CLINICAL_VIEW, Permission.CLINICAL_WRITE, Permission.USAGE_METRICS_VIEW},
    # Front desk sees only a "prescription issued" flag, never clinical content on screen; it may
    # print an issued prescription (RX_PRINT, spec D6).
    Role.FRONT_DESK: _EVERY_ROLE,
}


def permissions_for(role: Role, *, has_doctor_profile: bool) -> frozenset[Permission]:
    """What a member may do. An owner writes clinical records only if also a doctor (§8)."""
    granted = ROLE_PERMISSIONS[role]
    if role is Role.OWNER and has_doctor_profile:
        granted = granted | {Permission.CLINICAL_WRITE}
    return granted
