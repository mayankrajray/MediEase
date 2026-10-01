"""Platform endpoints: liveness and (from M0-P3) readiness.

``/health`` is **liveness** only — it answers "is the process up and serving?"
and must not touch the database or any dependency. Readiness (``/ready``, which
*does* check the database) arrives in M0-P3. Keeping them separate is the whole
point of the liveness/readiness distinction (CLAUDE.md "Docker / Service
Architecture").
"""

from __future__ import annotations

from flask import Blueprint, jsonify
from flask import Response as FlaskResponse

platform_bp = Blueprint("platform", __name__)


@platform_bp.get("/health")
def health() -> FlaskResponse:
    """Liveness probe. Always 200 while the process can serve requests."""
    return jsonify({"status": "ok"})
