# SynapseOS API Versioning Strategy

## Current State

All API endpoints are currently under the `/v1/` prefix. This document defines
how SynapseOS handles API versioning, deprecation, and migration going forward.

## Versioning Scheme

- **URL-based versioning**: `/v1/`, `/v2/`, etc.
- Each major version is a complete API surface — no minor versions in the URL.
- Minor/patch changes are backward-compatible within a major version.
- Only one version is actively served at a time (no parallel versions).

## What Constitutes a Major Version Change (v1 → v2)

Any of the following requires a new major version:

| Change Type | Example | Requires v2? |
|-------------|---------|-------------|
| Remove an endpoint | DELETE /v1/feedback | **Yes** |
| Rename a field | `answer` → `response` | **Yes** |
| Change a field type | `score: float` → `score: object` | **Yes** |
| Restructure response | Flat → nested | **Yes** |
| Add required field | New mandatory param | **Yes** |
| Add optional field | New optional param | No (backward compat) |
| Add new endpoint | POST /v1/admin/config | No (backward compat) |
| Add response field | New `metadata` in response | No (backward compat) |
| Change error format | New error codes | No (backward compat) |
| Performance improvement | Faster retrieval | No (backward compat) |

## Deprecation Policy

1. **Announcement**: Deprecated features are announced in the API changelog
   and marked with `deprecated: true` in the OpenAPI schema.
2. **Grace period**: 90 days from announcement to removal.
3. **Sunset header**: Deprecated endpoints return `Sunset: <date>` HTTP header.
4. **Warning header**: During grace period, responses include:
   ```
   Deprecation: true
   Link: <changelog-url>; rel="deprecation"
   ```

## Migration Guide Template (v1 → v2)

When v2 is introduced, this template will be filled out:

```markdown
## v1 → v2 Migration Guide

### Breaking Changes
| v1 Endpoint | v2 Equivalent | Notes |
|-------------|---------------|-------|
| POST /v1/query | POST /v2/query | `answer` renamed to `response` |
| ... | ... | ... |

### Field Mapping
| v1 Field | v2 Field | Type Change |
|----------|----------|-------------|
| answer | response | none |
| ... | ... | ... |

### Migration Steps
1. Update SDK to latest version
2. Update field names in client code
3. Test against /v2/ endpoints
4. Switch production traffic to /v2/
```

## Implementation Notes

- The FastAPI router uses `prefix="/v1"` for all current routes.
- Future versions will use `prefix="/v2"` with separate route modules.
- Shared business logic (services layer) is reused across versions.
- Only the route layer (request/response models) differs between versions.

## v1 Stability Commitment

The following v1 endpoints are **stable** and will not change without a major version:

| Endpoint | Stability |
|----------|-----------|
| POST /v1/query | **Stable** — field additions only |
| POST /v1/think | **Stable** — field additions only |
| POST /v1/ingest | **Stable** — field additions only |
| POST /v1/ingest/file | **Stable** — field additions only |
| POST /v1/feedback | **Stable** — no changes planned |
| GET /v1/collections | **Stable** — field additions only |
| GET /v1/analytics | **Stable** — field additions only |
| GET /health | **Stable** — will not change |

The following v1 endpoints are **evolving** and may receive backward-compatible additions:

| Endpoint | Status |
|----------|--------|
| POST /v1/keys | **Evolving** — new provider types may be added |
| POST /v1/tools | **Evolving** — new tool types may be added |
| GET /v1/sessions | **Evolving** — session features may expand |
| GET /v1/interactions | **Evolving** — filter/pagination may expand |
| WS /v1/ws/think | **Beta** — protocol may change |
| /admin/* | **Internal** — no stability guarantee |
