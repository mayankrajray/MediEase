"""WSGI entry point for gunicorn.

Run with, e.g.::

    gunicorn --bind 0.0.0.0:8000 mediease_api.wsgi:app

Settings are loaded and validated here (fail fast): an invalid environment makes
the worker exit non-zero at start-up rather than serving a broken app.
"""

from __future__ import annotations

from mediease_api.bootstrap import create_app
from mediease_api.config.settings import load_settings

app = create_app(load_settings())
