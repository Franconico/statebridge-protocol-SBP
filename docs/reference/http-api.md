---
title: HTTP API Reference
layout: default
---

# HTTP API Reference

All SBP REST endpoints are prefixed `/v1/sbp/` except the stateful proxy
endpoint at `/v1/chat/completions`.

**Base URL:** `http[s]://<host>`

Error responses follow the format:
```json
{ "error": { "code": "SBP_...", "message": "...", "detail": "..." } }
```

---

## L1 — Stateful Proxy

### `POST /v1/chat/completions`

OpenAI-compatible chat completions with optional `sbp` extension namespace.

**Request body:** `Content-Type: application/json`

| Field | Type | Required | Description |
|---|---|---|---|
| `model` | string | Yes | Any OpenAI-compatible model string. LLM-agnostic — passed through verbatim. |
| `messages` | array | Yes | Chat messages (OpenAI format). |
| `sbp` | object | No | SBP extension namespace. If absent, behaves as standard OpenAI proxy. |
| `sbp.force_new_session` | boolean | No | Default `false`. If `true`, ignore any suspended session. |
| `sbp.checkpoint_every` | integer ≥ 1 | No | Default `1`. Snapshot every N turns. |
| `sbp.memory_retrieval` | boolean | No | Default `true`. Inject retrieved memories into context. |

**Responses:**

- `200 OK` — Completed turn. Body includes `sbp.session_id`, `sbp.snapshot_id`, etc.
- `202 Accepted` — A suspended session was found. Body includes `sbp.resume_available: true` and `sbp.resume_prompt`.
- `400` — Malformed request.
- `500` — Internal server error.

---

## L3 — Roaming

### `POST /v1/sbp/sessions/{session_id}/export`

Export a session's full state into a signed, portable Roaming Token.

**Path params:** `session_id` (UUID)

**Request body:**

| Field | Type | Default | Description |
|---|---|---|---|
| `ttl_seconds` | integer [60, 604800] | 86400 | Token lifetime (1 min to 7 days). |
| `label` | string ≤ 120 chars | null | Human-readable label. |

**Responses:** `201 Created` — `export_id`, `roaming_token`, `expires_at`, `bundle_hash`, `message_count`, `label`.

`404` — Session not found (`SBP_SESSION_NOT_FOUND`).

---

### `POST /v1/sbp/sessions/import`

Import a Roaming Token into a new session on this server.

**Request body:**

| Field | Type | Default | Description |
|---|---|---|---|
| `roaming_token` | string | — | Required. The compact JWT from export. |
| `target_agent_id` | string | null | Override the target agent (default: original). |
| `allow_reuse` | boolean | false | If true, creates a fork instead of consuming the token. |

**Responses:** `201 Created` — `session_id`, `session_token`, `agent_id`, `step_count`, `message_count`, `provenance`.

`410 Gone` — Token expired or already consumed. `422` — Invalid token.

---

### `GET /v1/sbp/token/{roaming_token}`

Inspect a token without consuming it.

**Responses:** `200 OK` — `export_id`, `session_id`, `expires_at`, `imported_at`, `label`, `message_count`.

---

### `POST /v1/sbp/sessions/{session_id}/handoff`

Transfer context to a different agent (atomic export + import + bridge message + suspend).

**Request body:**

| Field | Type | Description |
|---|---|---|
| `to_agent_id` | string | Required. External ID of the destination agent. |
| `handoff_message` | string ≤ 2000 chars | Optional bridge message injected into the new session. |
| `reason` | string ≤ 500 chars | Optional reason for the handoff (logged for lineage). |

**Responses:** `201 Created` — `source_session_id`, `new_session_id`, `new_session_token`, `to_agent_id`, `export_id`.

---

### `POST /v1/sbp/sessions/{session_id}/fork`

Create a parallel branch from the current session checkpoint.

**Request body:**

| Field | Type | Description |
|---|---|---|
| `label` | string ≤ 120 chars | Optional human-readable name for the fork. |

**Responses:** `201 Created` — `fork_session_id`, `fork_session_token`, `fork_label`, `origin_session_id`, `fork_point_step`.

---

### `GET /v1/sbp/sessions/{session_id}/exports`

List all export records for a session.

**Responses:** `200 OK` — `{ "session_id": "...", "exports": [...] }`.

---

### `GET /v1/sbp/sessions/{session_id}/lineage`

Return the full family tree of a session.

**Responses:** `200 OK` — See [lineage.schema.json](../../spec/schemas/lineage.schema.json).

---

## L4/L5 — WebSocket

### `WS /v1/sbp/ws/{session_id}`

Live surface attachment endpoint. See [WebSocket Frames Reference](websocket-frames.md).

The first client frame MUST be `ATTACH_SESSION`. The server closes the connection
(code 1003) if any other frame arrives first.

---

## Error codes

| Code | HTTP | Meaning |
|---|---|---|
| `SBP_SESSION_NOT_FOUND` | 404 | Session does not exist |
| `SBP_TOKEN_EXPIRED` | 410 | Roaming Token has expired |
| `SBP_TOKEN_CONSUMED` | 410 | Token already imported |
| `SBP_TOKEN_INVALID` | 422 | Signature verification failed |
| `SBP_TOKEN_INTEGRITY` | 422 | Bundle hash mismatch |
| `SBP_INVALID_UUID` | 422 | Path parameter is not a valid UUID |
| `SBP_SESSION_CONFLICT` | 409 | Operation conflicts with current session state |
| `SBP_INTERNAL` | 500 | Unrecoverable server error |
