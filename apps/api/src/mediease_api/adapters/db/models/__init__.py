"""SQLAlchemy models. Importing this package registers every table on ``Base.metadata``.

Models are persistence shapes only; repositories map them to and from domain
entities, so nothing outside ``adapters/db`` ever sees a row object.
"""

from mediease_api.adapters.db.models.applications import (
    ClinicApplicationCheckRow,
    ClinicApplicationDoctorRow,
    ClinicApplicationRow,
)
from mediease_api.adapters.db.models.appointments import AppointmentRow, AppointmentStatusHistoryRow
from mediease_api.adapters.db.models.audit import AuditEventRow
from mediease_api.adapters.db.models.base import Base
from mediease_api.adapters.db.models.billing import (
    BillLineRow,
    BillRow,
    ClinicServiceRow,
    DoctorServicePriceRow,
    PaymentRow,
)
from mediease_api.adapters.db.models.booking import BookingRequestRow
from mediease_api.adapters.db.models.clinics import ClinicRow, DoctorRow, OnboardingChecklistRow
from mediease_api.adapters.db.models.identity import ClinicMembershipRow, RefreshTokenRow, UserRow
from mediease_api.adapters.db.models.jobs import JobRow
from mediease_api.adapters.db.models.links import PatientLinkRow, PublicRateLimitRow
from mediease_api.adapters.db.models.messages import MessageRow, WebhookEventRow
from mediease_api.adapters.db.models.notifications import NotificationPreferenceRow, NotificationRow
from mediease_api.adapters.db.models.patient_notifications import (
    PatientNotificationPreferenceRow,
    PatientNotificationRow,
)
from mediease_api.adapters.db.models.patients import PatientRow
from mediease_api.adapters.db.models.portal import (
    EmailTokenRow,
    ExternalIdentityRow,
    PatientAccountRow,
    PatientRefreshTokenRow,
)
from mediease_api.adapters.db.models.portal_links import (
    DoseRecordRow,
    MedicineReminderPrefRow,
    PatientAccountLinkRow,
    PatientPortalInviteRow,
)
from mediease_api.adapters.db.models.prescriptions import PrescriptionItemRow, PrescriptionRow
from mediease_api.adapters.db.models.reminders import ReminderRow
from mediease_api.adapters.db.models.rx_library import RxFavouriteRow, RxTemplateRow
from mediease_api.adapters.db.models.scheduling import (
    DoctorScheduleRow,
    ScheduleExceptionRow,
    SessionRow,
)
from mediease_api.adapters.db.models.subscriptions import ClinicSubscriptionRow
from mediease_api.adapters.db.models.uploads import PrescriptionUploadRow
from mediease_api.adapters.db.models.visits import VisitAddendumRow, VisitAttachmentRow, VisitRow

__all__ = [
    "AppointmentRow",
    "AppointmentStatusHistoryRow",
    "AuditEventRow",
    "Base",
    "BillLineRow",
    "BillRow",
    "BookingRequestRow",
    "ClinicApplicationCheckRow",
    "ClinicApplicationDoctorRow",
    "ClinicApplicationRow",
    "ClinicMembershipRow",
    "ClinicRow",
    "ClinicServiceRow",
    "ClinicSubscriptionRow",
    "DoctorRow",
    "DoctorScheduleRow",
    "DoctorServicePriceRow",
    "DoseRecordRow",
    "EmailTokenRow",
    "ExternalIdentityRow",
    "JobRow",
    "MedicineReminderPrefRow",
    "MessageRow",
    "NotificationPreferenceRow",
    "NotificationRow",
    "OnboardingChecklistRow",
    "PatientAccountLinkRow",
    "PatientAccountRow",
    "PatientLinkRow",
    "PatientNotificationPreferenceRow",
    "PatientNotificationRow",
    "PatientPortalInviteRow",
    "PatientRefreshTokenRow",
    "PatientRow",
    "PaymentRow",
    "PrescriptionItemRow",
    "PrescriptionRow",
    "PrescriptionUploadRow",
    "PublicRateLimitRow",
    "RefreshTokenRow",
    "ReminderRow",
    "RxFavouriteRow",
    "RxTemplateRow",
    "ScheduleExceptionRow",
    "SessionRow",
    "UserRow",
    "VisitAddendumRow",
    "VisitAttachmentRow",
    "VisitRow",
    "WebhookEventRow",
]
