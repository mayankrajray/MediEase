# ADR-0008: Contract-first API with OpenAPI and generated web types

| Field | Value |
|---|---|
| Status | Accepted |
| Date | 2026-09-15 |
| Related | contracts/openapi.yaml, API.md, TESTING.md |

## Context

Two codebases (Python and TypeScript), plus AI agents generating code on both sides, make drift
between API and client likely. Flask does not generate an OpenAPI document by itself.

## Decision

- `contracts/openapi.yaml` (OpenAPI 3.1) is the source of truth, edited in the same change as an
  endpoint.
- The web app generates TypeScript types from it (`make contract`); hand-written API types are not
  allowed.
- API contract tests validate real responses against the document in CI.

## Alternatives considered

| Option | Why not chosen |
|---|---|
| Code-first generation (flask-smorest, apispec) | Ties the contract to decorators in the delivery layer; agents edit code and forget the docs |
| No formal contract | Drift and runtime errors between web and API |
| GraphQL | Unneeded complexity for our CRUD-plus-workflow API |

## Consequences

- Slight duplication between Pydantic models and the YAML, caught by contract tests.
- The YAML becomes a useful prompt input for agents working on either side.
