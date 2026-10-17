"""Conditional GETs with a strong ETag (M3-P4; spec R12, decisions D23, D26).

The tag is a hash of the exact JSON bytes the response would carry, so any change a screen could
show — a new booking, a status, a corrected name, ``wait_minutes`` ticking over — changes it, and
nothing else does. ``If-None-Match`` is compared the way RFC 9110 §13.1.2 requires: weakly, with
``*`` matching any tag and a list matching if any member does. A match is ``304 Not Modified``
with the tag and no body; the blueprint's ``Cache-Control: no-store`` still applies, so no copy of
the queue (which holds names) is kept by a browser or a proxy: the client keeps it in memory.
"""

from __future__ import annotations

import hashlib
from typing import Any

from flask import Response, jsonify, request

TAG_LENGTH = 32  # hex characters of SHA-256: ample for telling two bodies of one URL apart


def strong_tag(body: bytes) -> str:
    return hashlib.sha256(body).hexdigest()[:TAG_LENGTH]


def conditional_json(body: dict[str, Any]) -> Response:
    """The JSON response with its strong ETag, or a bodiless 304 when the client has it."""
    response = jsonify(body)
    tag = strong_tag(response.get_data())
    if request.if_none_match.contains_weak(tag):
        not_modified = Response(status=304)
        not_modified.set_etag(tag)
        return not_modified
    response.set_etag(tag)
    return response
