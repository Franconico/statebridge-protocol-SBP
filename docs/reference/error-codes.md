---
title: Error Codes
layout: default
---

# Error Codes

## HTTP error response format

```json
{
  "error": {
    "code":    "SBP_SESSION_NOT_FOUND",
    "message": "Session 'abc123' not found",
    "detail":  "No conversation with ID abc123 exists in this deployment."
  }
}
```

## Error code table

| Code | HTTP Status | Meaning |
|---|---|---|
| `SBP_SESSION_NOT_FOUND` | 404 | The specified `session_id` does not exist. |
| `SBP_TOKEN_EXPIRED` | 410 | The Roaming Token's `exp` claim is in the past. |
| `SBP_TOKEN_CONSUMED` | 410 | The Roaming Token has already been imported (single-use default). |
| `SBP_TOKEN_INVALID` | 422 | Token signature verification failed (invalid secret, malformed JWT). |
| `SBP_TOKEN_INTEGRITY` | 422 | The bundle hash does not match the stored bundle (tampering or corruption). |
| `SBP_INVALID_UUID` | 422 | A path or body parameter expected to be a UUID is not a valid UUID format. |
| `SBP_SESSION_CONFLICT` | 409 | The requested operation conflicts with the session's current state (e.g. forking a completed session). |
| `SBP_INTERNAL` | 500 | An unrecoverable server error occurred. Inspect server logs. |

## WebSocket close codes

| Code | Meaning |
|---|---|
| 1000 | Normal closure (client sent `DETACH` or session completed). |
| 1003 | Protocol error — unexpected frame type or ordering violation. |
| 4003 | Forbidden — `session_token` is invalid or expired. |
| 4004 | Session not found — the `session_id` in `ATTACH_SESSION` does not exist. |
