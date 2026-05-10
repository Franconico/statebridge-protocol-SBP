---
title: Getting Started with SBP
layout: default
---

# Getting Started with SBP

This guide walks you from zero to an L5-conformant SBP session in under 5
minutes. You will install the reference server, send a stateful chat completion,
attach a surface, simulate a disconnection, and resume via the Tether drain.

**Prerequisites:** Python 3.11+, `wscat` (or any WebSocket client).

---

## 1. Install and start the reference server

The reference server is model-agnostic and server-agnostic: it routes LLM
calls to any OpenAI-compatible endpoint and uses an in-memory backend by
default (no database required for development).

```bash
pip install sbp-server-reference

# Set the model router endpoint and API key (any OpenAI-compatible provider)
export SBP_LLM_BASE_URL="https://api.openai.com/v1"    # or any compatible API
export SBP_LLM_API_KEY="sk-..."
export SBP_JWT_SECRET="change-me-to-a-256-bit-secret"

sbp-server start --port 8080
# → SBP reference server v1.2 running on http://localhost:8080
# → Backend: in-memory (single-process)
# → Conformance level: L5
```

> **Swap your LLM:** Set `SBP_LLM_BASE_URL` to any OpenAI-compatible endpoint —
> `https://api.anthropic.com/v1` for Claude, a local Ollama endpoint for Llama,
> a vLLM deployment for DeepSeek, etc. SBP passes the `model` field through verbatim.

---

## 2. Send your first stateful completion (L1)

```bash
curl -s -X POST http://localhost:8080/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -d '{
    "model": "gpt-4o",
    "messages": [
      {"role": "user", "content": "Plan a 3-day trip to Tokyo. Be concise."}
    ],
    "sbp": {
      "checkpoint_every": 1
    }
  }' | python3 -m json.tool
```

You should see a standard OpenAI response body with an added `sbp` field:

```json
{
  "choices": [...],
  "sbp": {
    "session_id":       "a1b2c3d4-...",
    "snapshot_id":      "b2c3d4e5-...",
    "resume_available": false,
    "step_count":       1,
    "cost_usd":         0.003
  }
}
```

Save the `session_id` — you'll use it in the next steps.

```bash
SESSION_ID="a1b2c3d4-..."  # paste your session_id here
```

---

## 3. Attach a surface via WebSocket (L4)

Open a WebSocket connection and attach the surface. The `ATTACH_SESSION` frame
declares this surface as a mobile device that supports Markdown and has a camera:

```bash
wscat -c ws://localhost:8080/v1/sbp/ws/$SESSION_ID
```

Once connected, send the `ATTACH_SESSION` frame (paste into wscat):

```json
{"type":"ATTACH_SESSION","session_id":"<SESSION_ID>","session_token":"<TOKEN>","surface_context":{"device_type":"mobile","ui_capabilities":["markdown","streaming"],"mcp_tools":["camera"]}}
```

The server responds with:

```json
{
  "type": "SESSION_ATTACHED",
  "session_id": "a1b2c3d4-...",
  "device_type": "mobile",
  "queued_turns": 0,
  "mcp_tools_registered": ["camera"],
  "sbp_version": "1.2",
  "sbp_level": "L5"
}
```

---

## 4. Simulate the Tether (L2)

Now close the WebSocket terminal (or press Ctrl+C). The server activates the
Tether — any turns produced while the surface is offline will be queued.

Send another completion from a different terminal:

```bash
curl -s -X POST http://localhost:8080/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -d "{
    \"model\": \"gpt-4o\",
    \"messages\": [
      {\"role\": \"user\", \"content\": \"Also add 3 restaurant recommendations.\"}
    ],
    \"sbp\": {\"checkpoint_every\": 1}
  }"
```

The agent responds (you'll see it in the HTTP response), but the surface is
offline. The response is queued in the Tether.

---

## 5. Resume and drain the Tether queue (L2)

Reconnect your WebSocket:

```bash
wscat -c ws://localhost:8080/v1/sbp/ws/$SESSION_ID
```

Send `ATTACH_SESSION` again. The server:
1. Confirms attachment.
2. Reports `"queued_turns": 1`.
3. Immediately sends the buffered `TETHER_TURN` frame with the restaurant
   recommendations.

```json
{
  "type": "TETHER_TURN",
  "turn_index": 0,
  "role": "assistant",
  "content": "For restaurants: 1) Sukiyabashi Jiro (sushi) 2) ...",
  "created_at": "2026-05-10T15:05:00Z"
}
```

The agent's work is preserved. Nothing was lost.

---

## 6. Export the session for roaming (L3)

Export the full session to a portable signed token:

```bash
curl -s -X POST http://localhost:8080/v1/sbp/sessions/$SESSION_ID/export \
  -H 'Content-Type: application/json' \
  -d '{"ttl_seconds": 3600, "label": "Tokyo trip"}' | python3 -m json.tool
```

```json
{
  "export_id":     "c3d4e5f6-...",
  "roaming_token": "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9...",
  "expires_at":    "2026-05-10T16:00:00Z",
  "message_count": 4
}
```

This token can be imported on **any** conformant SBP server — same provider,
different provider, or your own on-premises deployment. SBP is server-agnostic.

---

## What's next

- [**Concepts: Tether**](concepts/tether.md) — how the queue works
- [**Concepts: Roaming**](concepts/roaming.md) — export, import, handoff, fork
- [**Concepts: Surfaces**](concepts/surfaces.md) — SurfaceContext and device types
- [**Concepts: MCP Bridge**](concepts/mcp-bridge.md) — bidirectional tool calls
- [**HTTP API reference**](reference/http-api.md) — all endpoints
- [**WebSocket frames reference**](reference/websocket-frames.md) — all 13 frame types
- [**Conformance levels**](reference/conformance-levels.md) — checklists for L1–L5

---

## Changing your LLM

SBP is model-agnostic. To switch models mid-project:

```bash
# Switch from OpenAI to Anthropic
export SBP_LLM_BASE_URL="https://api.anthropic.com/v1"
export SBP_LLM_API_KEY="sk-ant-..."

sbp-server start --port 8080
```

Then in your requests, use the Claude model string:

```json
{ "model": "claude-opus-4-7", "messages": [...], "sbp": {} }
```

Sessions, snapshots, and roaming tokens are all model-agnostic — they record
which model was used per-turn in the message log, but the session itself has no
model affinity.
