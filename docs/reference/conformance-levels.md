---
title: Conformance Levels
layout: default
---

# Conformance Levels

SBP defines five conformance levels. An implementation that claims a level MUST
satisfy all requirements for that level and all levels below it.

To claim a conformance level, run the conformance suite against your server:

```bash
python conformance/runner.py --target http://localhost:8080 --level L5
```

And open a PR to add your implementation to [implementations.md](../implementations.md).

---

## L1 — Stateful Proxy

**What it adds:** The `sbp` namespace on `/v1/chat/completions`.

**Target effort:** An afternoon.

**Normative requirements:**

- [ ] `POST /v1/chat/completions` accepts a top-level `sbp` request object.
- [ ] When `sbp` is absent or null, the endpoint MUST behave as a standard OpenAI proxy (no session tracking).
- [ ] When `sbp` is present, the response MUST include `sbp.session_id` (UUID).
- [ ] The response MUST include `sbp.snapshot_id` (UUID or null) when a checkpoint was taken.
- [ ] The `model` field MUST be passed through verbatim to the LLM router — no model restrictions.
- [ ] HTTP 202 MUST be returned when a `suspended` session exists and `force_new_session` is false.
- [ ] HTTP 202 response MUST include `sbp.resume_available: true` and SHOULD include `sbp.resume_prompt`.

---

## L2 — Tether + Resume

**What it adds:** Session lifecycle, durable snapshots, WebSocket attach/drain.

**Target effort:** One week.

**Normative requirements (in addition to L1):**

- [ ] Sessions progress through the lifecycle states: `idle → running → suspended → completed | failed`.
- [ ] Sessions MUST be persisted; a server restart MUST NOT drop a `running` or `suspended` session.
- [ ] A `pre_action` snapshot MUST be written before any action with external side effects.
- [ ] A `post_action` snapshot MUST be written after each action completes.
- [ ] A `checkpoint` snapshot MUST be written every `checkpoint_every` turns.
- [ ] The Tether queue MUST be durable and cross-replica accessible (MUST NOT be in-process memory for multi-replica deployments).
- [ ] When a surface disconnects, the server MUST buffer subsequent output turns in the Tether queue.
- [ ] `WS /v1/sbp/ws/{session_id}` endpoint MUST exist.
- [ ] The first client frame MUST be `ATTACH_SESSION`; any other frame MUST cause a `PROTOCOL_ERROR` and close (code 1003).
- [ ] On `ATTACH_SESSION`, the server MUST validate `session_token`.
- [ ] `SESSION_ATTACHED` MUST be sent with `queued_turns` count and `sbp_version`.
- [ ] If `queued_turns > 0`, `TETHER_TURN` frames MUST follow immediately in chronological order.
- [ ] After drain, the Tether queue MUST be cleared.
- [ ] `DETACH` MUST activate the Tether.
- [ ] `PING` / `PONG` keepalive MUST be implemented.

---

## L3 — Roaming

**What it adds:** Export / import / handoff / fork / lineage REST API. Roaming Token (JWT). Bundle envelope.

**Target effort:** Two weeks.

**Normative requirements (in addition to L2):**

- [ ] `POST /v1/sbp/sessions/{id}/export` MUST return a compact HS256 JWT (`roaming_token`) with `sub`, `sid`, `iat`, `exp`.
- [ ] `ttl_seconds` MUST be in the range [60, 604800].
- [ ] The bundle MUST include `sbp_version`, `session`, `messages`, `memory`, `state_snapshot`, `metadata`.
- [ ] `memory.schema_id` MUST be a URI.
- [ ] `POST /v1/sbp/sessions/import` MUST verify the token signature and expiry.
- [ ] Import MUST mark the token consumed (single-use by default).
- [ ] Import with `allow_reuse: true` MUST create a Fork instead of consuming the token.
- [ ] If `memory.schema_id` is not recognized, the import MUST succeed without memory (MUST NOT reject).
- [ ] `GET /v1/sbp/token/{token}` MUST return metadata without consuming the token.
- [ ] `POST /v1/sbp/sessions/{id}/handoff` MUST be atomic: export + import + bridge message injection + source session suspension.
- [ ] `POST /v1/sbp/sessions/{id}/fork` MUST create an independent session sharing history through the fork point.
- [ ] `GET /v1/sbp/sessions/{id}/lineage` MUST return exports, outgoing/incoming handoffs, forks, and origin.
- [ ] Bundle hash MUST be verified on import; mismatch MUST return `SBP_TOKEN_INTEGRITY`.

---

## L4 — Surface Negotiation

**What it adds:** `SurfaceContext` in `ATTACH_SESSION`; server MAY adapt output.

**Target effort:** Days on top of L3.

**Normative requirements (in addition to L3):**

- [ ] `ATTACH_SESSION` MUST accept a `surface_context` object (as defined in `surface-context.schema.json`).
- [ ] Servers MUST tolerate absent, empty, or unknown `device_type` values without error.
- [ ] Servers MUST tolerate unknown `ui_capabilities` strings without error.
- [ ] `SESSION_ATTACHED` MUST echo the `device_type` from the surface context.
- [ ] Servers SHOULD respect `max_output_tokens` as an output length target.
- [ ] Servers MUST NOT fail or degrade for surfaces that send no `surface_context`.

---

## L5 — Surface MCP Bridge

**What it adds:** `TOOL_CALL` / `TOOL_RESULT` frames; bidirectional MCP over WebSocket.

**Target effort:** One week on top of L4.

**Normative requirements (in addition to L4):**

- [ ] When `surface_context.mcp_tools` is non-empty, the gateway MUST accept and register those tool names.
- [ ] `SESSION_ATTACHED` MUST include `mcp_tools_registered` listing the accepted tools.
- [ ] The gateway MUST NOT route `TOOL_CALL` for a tool not declared in `mcp_tools`.
- [ ] `TOOL_CALL` frames MUST include a unique `call_id` UUID.
- [ ] Multiple `TOOL_CALL` frames MAY be in-flight simultaneously (multiplexed by `call_id`).
- [ ] The gateway MUST apply a default 30-second timeout per tool call.
- [ ] On surface disconnect, all in-flight tool calls MUST be cancelled (treated as failed).
- [ ] `TOOL_RESULT` MUST be matched to the pending `TOOL_CALL` by `call_id`.
- [ ] On successful `TOOL_RESULT`, the result MUST be delivered to the LLM.

---

## Running the conformance suite

```bash
# Clone the spec repo
git clone https://github.com/statebridge-protocol/sbp.git
cd sbp

# Run against your server
python conformance/runner.py \
  --target http://your-sbp-server:8080 \
  --level L5 \
  --api-key "your-key"

# Run only a specific level
python conformance/runner.py --target http://localhost:8080 --level L1
```

The runner exits `0` on pass, `1` on failure. CI-friendly.
