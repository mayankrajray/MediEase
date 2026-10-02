"""Platform endpoints: liveness (``/health``) and readiness (``/ready``).

``/health`` answers "is the process up and serving?" and touches nothing else,
so a database outage never makes the container look dead and get restarted.
``/ready`` answers "can this instance handle traffic?" by proving the database
can execute a query within the readiness budget (CLAUDE.md "Health and
readiness are first-class").
"""

from __future__ import annotations

from flask import Blueprint, Response, jsonify

from mediease_api.ports.readiness import DatabaseCheck


def create_platform_blueprint(database_check: DatabaseCheck) -> Blueprint:
    """Build the platform blueprint around the injected readiness check."""
    bp = Blueprint("platform", __name__)

    @bp.get("/health")
    def health() -> Response:
        """Liveness probe. Always 200 while the process can serve requests."""
        return jsonify({"status": "ok"})

    @bp.get("/ready")
    def ready() -> Response:
        """Readiness probe. 200 when the database answers; otherwise the check
        raises a ReadinessError, which delivery/errors.py turns into a 503."""
        database_check.check()
        return jsonify({"status": "ready", "checks": {"database": "ok"}})

    return bp
