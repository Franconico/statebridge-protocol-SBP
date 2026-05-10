---
title: WebSocket Frames Reference
layout: default
---

# WebSocket Frame Reference

All frames are JSON objects with a `"type"` string discriminator. Unknown frame
types MUST be silently ignored (forward-compatible extension point).

**Ordering rule:** The first frame from the client MUST be `ATTACH_SESSION`.
The server MUST close (code 1003) if any other frame arrives first.

**Endpoint:** `ws[s]://<host>/v1/sbp/ws/{session_id}`

---

## Client → Server

### `ATTACH_SESSION`

Must be sent as the very first frame. Authenticates the surface and declares its
capabilities.

```json
{
  "type":            "ATTACH_SESSION",
  "session_id":      "uuid",
  "session_token":   "string",
  "surface_context": {
    "device_type":       "mobile",
    "max_output_tokens": 300,
    "ui_capabilities":   ["markdown", "streaming"],
    "locale":            "en-US",
    "surface_id":        "uuid-or-fingerprint",
    "mcp_tools":         ["camera", "gps"]
  }
}
```

| Field | Required | Description |
|---|---|---|
| `session_id` | Yes | Must match the URL path parameter. |
| `session_token` | Yes | Authentication credential for this session. |
| `surface_context` | No | See [SurfaceContext schema](../../spec/schemas/surface-context.schema.json). |

---

### `DETACH`

Graceful disconnect. The server activates the Tether on receipt.

```json
{ "type": "DETACH" }
```

---

### `TOOL_RESULT`

Reply to a `TOOL_CALL` from the server. Must be sent within the timeout
(default: 30 seconds).

```json
{
  "type":    "TOOL_RESULT",
  "call_id": "uuid",
  "result":  { ... },
  "error":   null
}
```

| Field | Required | Description |
|---|---|---|
| `call_id` | Yes | Must match the `call_id` from the corresponding `TOOL_CALL`. |
| `result` | No | Tool output object. Structure is tool-specific. |
| `error` | No | Error string if the tool failed; null on success. |

---

### `PONG`

Reply to a server `PING`. Must be sent within 10 seconds or the server MAY
close the connection.

```json
{ "type": "PONG" }
```

---

## Server → Client

### `SESSION_ATTACHED`

Sent immediately after successful `ATTACH_SESSION` validation.

```json
{
  "type":                  "SESSION_ATTACHED",
  "session_id":            "uuid",
  "surface_id":            "uuid or null",
  "device_type":           "mobile",
  "queued_turns":          3,
  "mcp_tools_registered":  ["camera", "gps"],
  "sbp_version":           "1.2",
  "sbp_level":             "L5"
}
```

`queued_turns` is the number of Tether turns about to be delivered. If > 0,
`TETHER_TURN` frames follow immediately.

---

### `SESSION_NOT_FOUND`

```json
{ "type": "SESSION_NOT_FOUND", "detail": "No session with ID abc123" }
```

Server closes after sending (code 4004).

---

### `FORBIDDEN`

```json
{ "type": "FORBIDDEN", "detail": "session_token invalid or expired" }
```

Server closes after sending (code 4003).

---

### `PROTOCOL_ERROR`

```json
{ "type": "PROTOCOL_ERROR", "detail": "Expected ATTACH_SESSION as first frame, got 'PONG'" }
```

Server closes after sending (code 1003).

---

### `TETHER_TURN`

Delivers a buffered turn from the Tether queue. Sent in chronological order
after `SESSION_ATTACHED` when `queued_turns > 0`.

```json
{
  "type":       "TETHER_TURN",
  "turn_index": 0,
  "role":       "assistant",
  "content":    "Here is what I found while you were away...",
  "model_used": "gpt-4o",
  "created_at": "2026-05-10T15:05:00Z"
}
```

---

### `TURN_CHUNK`

Streaming output chunk. Part of a multi-chunk turn.

```json
{
  "type":     "TURN_CHUNK",
  "chunk_id": "uuid",
  "delta":    "partial text content..."
}
```

---

### `TURN_COMPLETE`

Signals the end of a streaming turn.

```json
{ "type": "TURN_COMPLETE", "chunk_id": "uuid" }
```

---

### `TOOL_CALL`

Sent when the agent requests a surface-side MCP tool call. The surface MUST
reply with `TOOL_RESULT` within the timeout (default: 30 seconds).

```json
{
  "type":       "TOOL_CALL",
  "call_id":    "uuid",
  "tool_name":  "camera",
  "tool_input": { "mode": "photo", "facing": "back" }
}
```

Multiple `TOOL_CALL` frames may be in-flight simultaneously; they are
correlated by `call_id`.

---

### `PING`

Keepalive. Client MUST reply with `PONG` within 10 seconds.

```json
{ "type": "PING" }
```

---

## WebSocket close codes

| Code | Meaning |
|---|---|
| 1000 | Normal closure |
| 1003 | Protocol error (bad frame type or ordering) |
| 4003 | Forbidden (invalid session_token) |
| 4004 | Session not found |
