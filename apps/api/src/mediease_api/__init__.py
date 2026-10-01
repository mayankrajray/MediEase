"""MediEase API package.

A hexagonal Flask backend. The composition root (``bootstrap.create_app``)
wires configuration, logging, middleware and routes with no import-time side
effects. See ``docs/ARCHITECTURE.md`` and ``AGENTS.md`` §3 for the layer map.
"""

__all__ = ["__version__"]

__version__ = "0.0.0"
