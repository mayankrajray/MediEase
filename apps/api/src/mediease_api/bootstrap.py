"""Composition root — the Flask application factory.

CLAUDE.md ("Composition root"): configuration, logging, adapters, middleware and
routes are wired in exactly one place, with **no import-time side effects**.
Importing this module does nothing; only calling ``create_app(settings)`` builds
an app. This is also the only place that chooses adapters (apps/api/CLAUDE.md).
"""

from __future__ import annotations

import secrets
from dataclasses import dataclass
from datetime import timedelta

import structlog
from flask import Flask
from sqlalchemy.orm import Session, sessionmaker

from mediease_api.adapters.clock.system import SystemClock
from mediease_api.adapters.db.engine import build_engine
from mediease_api.adapters.db.readiness import SqlAlchemyDatabaseCheck
from mediease_api.adapters.db.unit_of_work import SqlAlchemyUnitOfWork, build_session_factory
from mediease_api.adapters.ids.uuid7 import Uuid7Generator
from mediease_api.adapters.security.argon2_hasher import Argon2PasswordHasher
from mediease_api.adapters.security.ip_hash import HmacIpHasher
from mediease_api.adapters.security.jwt_tokens import JwtAccessTokenIssuer
from mediease_api.adapters.security.refresh_secrets import Sha256RefreshTokenSecrets
from mediease_api.application.auth._session import SessionIssuer
from mediease_api.application.auth.authenticate import AuthenticateRequest
from mediease_api.application.auth.refresh_session import RefreshSession
from mediease_api.application.auth.sign_in import SignIn
from mediease_api.application.auth.sign_out import SignOut
from mediease_api.application.clinics.change_staff_role import ChangeStaffRole
from mediease_api.application.clinics.deactivate_staff import DeactivateStaff
from mediease_api.application.clinics.invite_staff import InviteStaff
from mediease_api.application.clinics.onboard_clinic import (
    AddDoctor,
    CreateClinic,
    UpdateClinic,
    UpdateDoctor,
)
from mediease_api.application.clinics.queries import GetClinic, GetDoctor, ListDoctors, ListStaff
from mediease_api.application.identity.accept_invite import AcceptInvite, DescribeInvite
from mediease_api.application.ops.queries import GetClinicOnboarding, ListClinics
from mediease_api.application.patients.consent import OptIn, OptOut, RecordConsent
from mediease_api.application.patients.import_patients import ImportPatients
from mediease_api.application.patients.queries import GetPatient, LookupPatients
from mediease_api.application.patients.register_patient import RegisterPatient
from mediease_api.application.patients.update_patient import UpdatePatient
from mediease_api.config.logging import configure_logging
from mediease_api.config.settings import AppSettings
from mediease_api.delivery.errors import register_error_handlers
from mediease_api.delivery.http.access import check_every_route_has_policy, register_access_control
from mediease_api.delivery.http.auth import create_auth_blueprint
from mediease_api.delivery.http.clinic import create_clinic_blueprint
from mediease_api.delivery.http.csrf import register_csrf_protection
from mediease_api.delivery.http.invites import create_invite_blueprint
from mediease_api.delivery.http.me import create_me_blueprint
from mediease_api.delivery.http.ops import create_ops_blueprint
from mediease_api.delivery.http.patients import create_patients_blueprint
from mediease_api.delivery.http.platform import create_platform_blueprint
from mediease_api.delivery.http.request_info import register_request_info
from mediease_api.delivery.middleware import register_request_middleware
from mediease_api.ports.clock import ClockPort
from mediease_api.ports.ids import IdPort
from mediease_api.ports.readiness import DatabaseCheck
from mediease_api.ports.security import AccessTokenIssuer, PasswordHasher
from mediease_api.ports.unit_of_work import UnitOfWork

logger = structlog.get_logger(__name__)


@dataclass(frozen=True, slots=True)
class _UseCases:
    """Builds each use case with a fresh unit of work, once per request.

    The HTTP blueprints each declare the subset they need as a Protocol, so
    this one container satisfies all of them structurally without any of them
    depending on the others.
    """

    session_factory: sessionmaker[Session]
    clock: ClockPort
    ids: Uuid7Generator
    hasher: PasswordHasher
    refresh_secrets: Sha256RefreshTokenSecrets
    # The same adapter: an invitation needs exactly what a refresh token needs
    # — an unguessable value stored only as a digest (ports/security.py).
    invite_secrets: Sha256RefreshTokenSecrets
    access_tokens: AccessTokenIssuer
    sessions: SessionIssuer
    dummy_password_hash: str

    def sign_in(self) -> SignIn:
        return SignIn(
            uow=self._uow(),
            clock=self.clock,
            ids=self.ids,
            hasher=self.hasher,
            sessions=self.sessions,
            dummy_password_hash=self.dummy_password_hash,
        )

    def refresh(self) -> RefreshSession:
        return RefreshSession(
            uow=self._uow(),
            clock=self.clock,
            ids=self.ids,
            secrets=self.refresh_secrets,
            sessions=self.sessions,
        )

    def sign_out(self) -> SignOut:
        return SignOut(
            uow=self._uow(), clock=self.clock, ids=self.ids, secrets=self.refresh_secrets
        )

    def authenticate(self) -> AuthenticateRequest:
        return AuthenticateRequest(
            uow=self._uow(), clock=self.clock, access_tokens=self.access_tokens
        )

    def get_clinic(self) -> GetClinic:
        return GetClinic(uow=self._uow())

    def update_clinic(self) -> UpdateClinic:
        return UpdateClinic(uow=self._uow(), clock=self.clock, ids=self.ids)

    def list_doctors(self) -> ListDoctors:
        return ListDoctors(uow=self._uow())

    def get_doctor(self) -> GetDoctor:
        return GetDoctor(uow=self._uow())

    def add_doctor(self) -> AddDoctor:
        return AddDoctor(uow=self._uow(), clock=self.clock, ids=self.ids)

    def update_doctor(self) -> UpdateDoctor:
        return UpdateDoctor(uow=self._uow(), clock=self.clock, ids=self.ids)

    def list_staff(self) -> ListStaff:
        return ListStaff(uow=self._uow())

    def invite_staff(self) -> InviteStaff:
        return InviteStaff(
            uow=self._uow(), clock=self.clock, ids=self.ids, secrets=self.invite_secrets
        )

    def change_staff_role(self) -> ChangeStaffRole:
        return ChangeStaffRole(uow=self._uow(), clock=self.clock, ids=self.ids)

    def deactivate_staff(self) -> DeactivateStaff:
        return DeactivateStaff(uow=self._uow(), clock=self.clock, ids=self.ids)

    def describe_invite(self) -> DescribeInvite:
        return DescribeInvite(uow=self._uow(), clock=self.clock, secrets=self.invite_secrets)

    def accept_invite(self) -> AcceptInvite:
        return AcceptInvite(
            uow=self._uow(),
            clock=self.clock,
            ids=self.ids,
            hasher=self.hasher,
            secrets=self.invite_secrets,
            sessions=self.sessions,
        )

    def create_clinic(self) -> CreateClinic:
        return CreateClinic(uow=self._uow(), clock=self.clock, ids=self.ids)

    def register_patient(self) -> RegisterPatient:
        return RegisterPatient(uow=self._uow(), clock=self.clock, ids=self.ids)

    def update_patient(self) -> UpdatePatient:
        return UpdatePatient(uow=self._uow(), clock=self.clock, ids=self.ids)

    def get_patient(self) -> GetPatient:
        return GetPatient(uow=self._uow(), clock=self.clock)

    def lookup_patients(self) -> LookupPatients:
        return LookupPatients(uow=self._uow(), clock=self.clock)

    def record_consent(self) -> RecordConsent:
        return RecordConsent(uow=self._uow(), clock=self.clock, ids=self.ids)

    def opt_out(self) -> OptOut:
        return OptOut(uow=self._uow(), clock=self.clock, ids=self.ids)

    def opt_in(self) -> OptIn:
        return OptIn(uow=self._uow(), clock=self.clock, ids=self.ids)

    def import_patients(self) -> ImportPatients:
        return ImportPatients(uow=self._uow(), clock=self.clock, ids=self.ids)

    def list_clinics(self) -> ListClinics:
        return ListClinics(uow=self._uow())

    def get_clinic_onboarding(self) -> GetClinicOnboarding:
        return GetClinicOnboarding(uow=self._uow())

    def _uow(self) -> SqlAlchemyUnitOfWork:
        return SqlAlchemyUnitOfWork(self.session_factory)


def build_password_hasher() -> PasswordHasher:
    """Production Argon2id parameters (also used by ``make seed``)."""
    return Argon2PasswordHasher()


@dataclass(frozen=True, slots=True)
class SeedDependencies:
    uow: UnitOfWork
    clock: ClockPort
    ids: IdPort
    hasher: PasswordHasher


def build_seed_dependencies(settings: AppSettings) -> SeedDependencies:
    """Adapters for ``delivery/cli/seed.py``, chosen here like everything else."""
    configure_logging(settings)
    return SeedDependencies(
        uow=SqlAlchemyUnitOfWork(build_session_factory(build_engine(settings))),
        clock=SystemClock(),
        ids=Uuid7Generator(),
        hasher=build_password_hasher(),
    )


def create_app(
    settings: AppSettings,
    *,
    database_check: DatabaseCheck | None = None,
    password_hasher: PasswordHasher | None = None,
    clock: ClockPort | None = None,
) -> Flask:
    """Build and wire the Flask application from validated settings.

    The keyword arguments replace adapters in tests: a fake readiness check, a
    cheap password hasher, a fixed clock. Building the engine opens no
    connection, so this stays side-effect free.
    """
    configure_logging(settings)

    engine = build_engine(settings)
    if database_check is None:
        database_check = SqlAlchemyDatabaseCheck(engine)

    clock = clock or SystemClock()
    ids = Uuid7Generator()
    hasher = password_hasher or build_password_hasher()
    refresh_secrets = Sha256RefreshTokenSecrets()
    access_tokens = JwtAccessTokenIssuer(
        signing_key=settings.JWT_SIGNING_KEY.get_secret_value(),
        ttl=timedelta(seconds=settings.ACCESS_TOKEN_TTL_SECONDS),
        ids=ids,
    )
    use_cases = _UseCases(
        session_factory=build_session_factory(engine),
        clock=clock,
        ids=ids,
        hasher=hasher,
        refresh_secrets=refresh_secrets,
        invite_secrets=refresh_secrets,
        access_tokens=access_tokens,
        sessions=SessionIssuer(
            ids=ids,
            secrets=refresh_secrets,
            access_tokens=access_tokens,
            refresh_ttl=timedelta(seconds=settings.REFRESH_TOKEN_TTL_SECONDS),
        ),
        # One real hash of a random password, so unknown accounts cost the
        # same verification as real ones (spec R2).
        dummy_password_hash=hasher.hash(secrets.token_urlsafe(32)),
    )

    # static_folder=None: the API serves JSON only, so there is no static route
    # to exempt from the access policy check below.
    app = Flask(__name__, static_folder=None)
    # Keep the validated settings on the app for handlers that need them later.
    app.config["SETTINGS"] = settings

    # Order matters: request context is bound first, then the request's ID and
    # IP fingerprint, then CSRF is checked (it costs no database call), then
    # each route's access policy decides who may continue; error handlers wrap
    # everything so failures still carry the request_id.
    register_request_middleware(app)
    register_request_info(app, HmacIpHasher(settings.AUDIT_IP_SALT.get_secret_value()))
    register_csrf_protection(app)
    register_access_control(app, use_cases)
    register_error_handlers(app)
    app.register_blueprint(create_platform_blueprint(database_check))
    app.register_blueprint(create_auth_blueprint(use_cases, cookie_secure=settings.COOKIE_SECURE))
    app.register_blueprint(create_invite_blueprint(use_cases, cookie_secure=settings.COOKIE_SECURE))
    app.register_blueprint(create_me_blueprint())
    app.register_blueprint(
        create_clinic_blueprint(use_cases, public_base_url=settings.PUBLIC_BASE_URL)
    )
    app.register_blueprint(
        create_ops_blueprint(use_cases, public_base_url=settings.PUBLIC_BASE_URL)
    )
    app.register_blueprint(create_patients_blueprint(use_cases))
    # Default deny: refuse to start with an undeclared route (spec R6-R10).
    check_every_route_has_policy(app)

    logger.info("app.created", app_env=settings.APP_ENV.value)
    return app
