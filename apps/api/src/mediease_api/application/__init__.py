"""Application layer: one use case per user action, plus job handlers.

Depends only on `domain` and `ports`; adapters are injected by the composition
root (apps/api/CLAUDE.md "Layer rules"). Enforced by import-linter in
`make lint` and CI (pyproject.toml [tool.importlinter]). The first use cases
arrive in M1.
"""
