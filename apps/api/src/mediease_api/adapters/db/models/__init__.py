"""SQLAlchemy models. Importing this package registers every table on ``Base.metadata``.

Models are persistence shapes only; repositories map them to and from domain
entities, so nothing outside ``adapters/db`` ever sees a row object.
"""

from mediease_api.adapters.db.models.audit import AuditEventRow
from mediease_api.adapters.db.models.base import Base
from mediease_api.adapters.db.models.clinics import ClinicRow, DoctorRow
from mediease_api.adapters.db.models.identity import ClinicMembershipRow, RefreshTokenRow, UserRow

__all__ = [
    "AuditEventRow",
    "Base",
    "ClinicMembershipRow",
    "ClinicRow",
    "DoctorRow",
    "RefreshTokenRow",
    "UserRow",
]
