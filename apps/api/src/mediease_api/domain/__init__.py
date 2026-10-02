"""Domain layer: entities, value objects, state machines and domain errors.

Standard library only — no framework, ORM, validation or logging library
(apps/api/CLAUDE.md "Layer rules"). Enforced by import-linter in `make lint` and
CI (pyproject.toml [tool.importlinter]).

- ``shared/``   errors, phone and email value objects, text and time rules
- ``clinics/``  Clinic (the tenant) and Doctor
- ``identity/`` User and ClinicMembership (roles)
"""
