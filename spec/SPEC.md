# State Bridge Protocol (SBP)
## Specification v1.2

**Status:** Draft — v1.2 (initial public release)
**Date:** 2026-05-10
**Repository:** https://github.com/statebridge-protocol/sbp
**License:** Apache-2.0

---

## Abstract

The State Bridge Protocol (SBP) is an open, model-agnostic, server-agnostic
protocol for the **Northbound** layer of AI agent systems — the channel between
an AI agent and the human it serves across devices, time, and disconnections.

SBP gives agents a persistent identity that survives WebSocket drops, device
switches, and even a transfer to a different agent entirely. It defines how
sessions are created, checkpointed, roamed across devices, and how surfaces
(phones, watches, browsers, voice assistants) communicate their capabilities to
the gateway — including the ability to expose their own MCP tools for the agent
to call.

SBP is intentionally **complementary to MCP** (Model Context Protocol). MCP is
the Southbound protocol (agent ↔ databases, APIs, files). SBP is the Northbound
protocol (agent ↔ human). They compose; they do not compete.

---

## Status of This Document

This is the initial public specification of SBP. It reflects the wire protocol
as currently implemented by the MARGNE-AI reference implementation (SilkBridge).
Earlier internal wire versions (1.0, 1.1) are considered pre-history.

The key words **MUST**, **MUST NOT**, **REQUIRED**, **SHALL**, **SHALL NOT**,
**SHOULD**, **SHOULD NOT**, **RECOMMENDED**, **MAY**, and **OPTIONAL** in this
document are to be interpreted as described in [RFC 2119].

---

## Table of Contents

1. [Introduction](#1-introduction)
2. [Design Principles](#2-design-principles)
3. [Terminology](#3-terminology)
4. [Protocol Overview](#4-protocol-overview)
5. [Conformance Levels](#5-conformance-levels)
6. [L1 — Stateful Proxy](#6-l1--stateful-proxy)
7. [L2 — Tether and Resume](#7-l2--tether-and-resume)
8. [L3 — Roaming](#8-l3--roaming)
9. [L4 — Surface Negotiation](#9-l4--surface-negotiation)
10. [L5 — Surface MCP Bridge](#10-l5--surface-mcp-bridge)
11. [WebSocket Frame Catalog](#11-websocket-frame-catalog)
12. [Error Model](#12-error-model)
13. [Security Considerations](#13-security-considerations)
14. [MCP Interoperability](#14-mcp-interoperability)
15. [IANA and Registry Considerations](#15-iana-and-registry-considerations)
16. [References](#16-references)
17. [Appendix A — JSON Schemas](#appendix-a--json-schemas)
18. [Appendix B — Worked Examples](#appendix-b--worked-examples)
19. [Appendix C — Change History](#appendix-c--change-history)

---

## 1. Introduction

AI agents today are stateless by default. The large language models (LLMs) that
power them are stateless — each inference call receives a full context window
and returns a response. The protocol that routes tool calls to databases (MCP)
is stateless — each call is independent. The WebSocket connections that stream
responses to the user are ephemeral — a disconnection loses everything.

This statelessness is appropriate for the Southbound layer (agent ↔ tools). It
is catastrophically wrong for the Northbound layer (agent ↔ human). Humans are
not stateless. They put their phone down and pick it up an hour later. They
switch from their laptop to their watch. They hand a task to a colleague. They
expect the agent to remember.

SBP defines the Northbound layer: a session abstraction that persists across
disconnections (the **Tether**), a mechanism to transfer that session to any
device or deployment (the **Roaming**), a way for surfaces to announce their
capabilities (the **Surface**), and a bidirectional bridge that lets the agent
call tools that live on the surface — a camera, the user's contacts, a GPS
reading — through the same WebSocket connection (the **MCP Bridge**).

### 1.1 Relationship to MCP

SBP and MCP are designed to compose:

```
[Surface: Apple Watch]  ←──(SBP Northbound)──→  [Agent Gateway]  ←──(MCP Southbound)──→  [Enterprise DB]
```

MCP defines how agents talk *down* to the machine world. SBP defines how agents
talk *up* to the human world. An agent gateway SHOULD implement both. A surface
SHOULD speak SBP. A tool server SHOULD speak MCP. Neither replaces the other.

SBP also carries MCP: when a surface announces `mcp_tools: ["camera", "gps"]`,
it becomes an MCP server reachable through the SBP WebSocket. The gateway routes
MCP tool-call requests down to the surface and delivers the results back up to
the LLM — all through the SBP frame protocol (see §10 and §14).

### 1.2 Model and server agnosticism

SBP is **model-agnostic** and **server-agnostic** by design. These are
first-class design goals, not implementation details:

**Model-agnostic:** The only LLM-specific field in the entire protocol is the
`model` string in the request envelope (§6.1). This field accepts any
OpenAI-compatible model identifier. Implementations are free to route to Claude,
GPT-4o, Llama 4, DeepSeek, Gemini, a fine-tuned local model, or any future
model. Sessions survive model changes — an operator can swap the underlying LLM
for a running session without the surface or the user observing any difference.
No clause in this spec requires a specific LLM or a specific LLM provider.

**Server-agnostic:** The backend requirements of SBP (session storage, durable
queuing, snapshot persistence, token storage) are defined as abstract interfaces,
not as specific technologies. An implementation MAY use PostgreSQL or SQLite or
DynamoDB for session storage. It MAY use Redis, Temporal, Kafka, or an in-process
queue for the Tether. It MAY use any HMAC-compatible signing library for tokens.
The only normative requirement is the *contract* (what the backend MUST
guarantee), not the implementation. This allows institutions to deploy SBP
entirely on-premises, in air-gapped environments, or on sovereign cloud
infrastructure, with no dependency on any third-party service.

---

## 2. Design Principles

The following principles govern the design of SBP and MUST inform future spec
changes:

1. **Vendor neutrality** — The spec MUST NOT mandate a specific LLM, cloud
   provider, database, orchestration engine, or programming language.

2. **Institutional sovereignty** — Any institution MUST be able to deploy a
   fully conformant SBP implementation without any network calls to third-party
   services. An air-gapped hospital running local Llama models MUST be a
   first-class use case.

3. **Composability with MCP** — SBP MUST NOT duplicate MCP functionality. Where
   they overlap (tool calls), SBP SHOULD route through MCP rather than define
   a parallel tool system.

4. **Minimal surface area** — The spec defines the minimum set of contracts
   required for interoperability. Optional features SHOULD be OPTIONAL; required
   features MUST be justified by universal need.

5. **Implementer accessibility** — An L1 implementation MUST be achievable in
   an afternoon. An L5 implementation MUST be achievable by a small team. The
   spec MUST NOT assume Temporal, Kubernetes, or any specific operational
   platform.

6. **Stability over novelty** — Breaking changes incur a major version bump and
   a migration path. The spec SHOULD prefer additive evolution.

---

## 3. Terminology

**Agent** — A software system that uses an LLM to pursue a goal over multiple
turns, potentially across time, devices, and sessions.

**Session** — A single continuous run of an agent, identified by a `session_id`.
A session progresses through a lifecycle of states (§7.2). One agent may have
many sessions over time, but only one active session at a time.

**Tether** — The mechanism by which an SBP server buffers agent output turns
that occur while no surface is attached. When a surface reattaches, buffered
turns are drained through the live connection. The Tether is what allows the
agent to keep working even when the user's device is offline.

**Surface** — A client that attaches to a session via WebSocket. A surface
represents a physical device or rendering context (phone, watch, browser,
voice assistant, IoT device). One session has at most one attached surface at
a time in v1.2.

**SurfaceContext** — A descriptor sent by the surface at attach time, declaring
its device type, output capabilities, locale, and the local MCP tools it exposes.

**Snapshot** — A durable serialization of the agent's full state at a point in
time. Used for crash recovery and as the basis for export bundles.

**Roaming Token** — A signed, time-limited JWT that encapsulates a reference to
an export bundle. Presenting the token to any SBP gateway allows importing the
session state into a new session.

**Bundle** — The full exported state of a session: messages, memory, snapshot,
and provenance metadata. Stored server-side; the Roaming Token is a reference
to it.

**Handoff** — An atomic operation that exports a session, creates a new session
under a different agent with the bundle imported, injects a bridge message, and
suspends the source session.

**Fork** — An operation that creates a new session that shares all history up to
the fork point with the origin session, then diverges independently.

**Lineage** — The graph of relationships among sessions: exports, handoffs (in
and out), forks, and the fork origin.

**MCP Bridge** — The SBP mechanism by which surface-declared MCP tools are made
callable by the agent through `TOOL_CALL` / `TOOL_RESULT` WebSocket frames.

**Conformance Level** — One of L1–L5, indicating which SBP capabilities an
implementation supports (§5).

---

## 4. Protocol Overview

SBP operates on two channels:

**Control plane (HTTP/JSON):** REST endpoints for session management, roaming
operations (export, import, handoff, fork, lineage), and session inspection.
All control-plane requests use JSON bodies and JSON responses. All endpoints
are prefixed `/v1/sbp/` except the stateful proxy endpoint `/v1/chat/completions`.

**Data plane (WebSocket/JSON):** A persistent WebSocket connection between a
surface and the gateway, used for streaming turns, draining the Tether queue,
and bidirectional MCP tool calls. The WebSocket URL is
`ws[s]://<host>/v1/sbp/ws/<session_id>`.

Both channels are transport-agnostic in principle: the normative wire format is
JSON over HTTP/1.1 or HTTP/2 (control plane) and JSON-framed WebSocket
(data plane). Future versions of this spec MAY define alternative transports
(e.g. gRPC, QUIC) as long as the semantic contracts are preserved.

### 4.1 Versioning

The protocol version is a `major.minor` string (e.g. `"1.2"`). It is
advertised by the server in the `SESSION_ATTACHED` frame's `sbp_version` field.
Clients SHOULD check this field and MAY refuse to operate if the version is
incompatible.

Export bundles carry a separate `sbp_version` field (currently `"1.0"`)
identifying the bundle format version. The bundle version and the wire version
are independent version streams.

Minor version bumps are backwards-compatible additions. Major version bumps
indicate breaking changes.

---

## 5. Conformance Levels

SBP defines five conformance levels. An implementation declares its level;
it MUST satisfy all normative requirements for that level and all levels
below it.

| Level | Name | What it adds |
|-------|------|-------------|
| **L1** | Stateful Proxy | `sbp` namespace on `/v1/chat/completions`; session and snapshot identifiers in responses |
| **L2** | Tether + Resume | Session lifecycle state machine; pre/post-action snapshots; Tether queue; WebSocket attach/drain |
| **L3** | Roaming | Export/import/handoff/fork/lineage REST API; Roaming Token (JWT); bundle envelope |
| **L4** | Surface Negotiation | `SurfaceContext` in `ATTACH_SESSION`; server MAY adapt output based on surface capabilities |
| **L5** | Surface MCP Bridge | `TOOL_CALL` / `TOOL_RESULT` frames; bidirectional MCP over WebSocket |

Implementations MAY implement levels out of order, but MUST satisfy all
requirements of every level up to and including the claimed level. An
implementation that claims L3 but does not implement L2 is non-conformant.

The MARGNE-AI reference implementation (SilkBridge) is L5-conformant.

### 5.1 Advertising conformance

A conformant server SHOULD advertise its level in the `SESSION_ATTACHED` frame:

```json
{
  "type": "SESSION_ATTACHED",
  "sbp_version": "1.2",
  "sbp_level": "L5",
  ...
}
```

The `sbp_level` field is OPTIONAL in v1.2 but RECOMMENDED.

---

## 6. L1 — Stateful Proxy

L1 adds a minimal `sbp` namespace to the OpenAI-compatible chat completions
endpoint. It is the entry point: an existing OpenAI client that adds `"sbp": {}`
to its request body gains session tracking and snapshot identifiers with no
other changes.

### 6.1 Request envelope

`POST /v1/chat/completions`

The request body is the standard OpenAI chat completions body plus a top-level
`sbp` object:

```jsonc
{
  "model": "gpt-4o",          // any OpenAI-compatible model string — LLM-agnostic
  "messages": [...],
  "stream": false,
  // ... standard OpenAI fields ...

  "sbp": {                     // OPTIONAL; omit for pure OpenAI passthrough
    "force_new_session": false, // OPTIONAL boolean — force a new session even if one exists
    "checkpoint_every": 1,      // OPTIONAL integer ≥ 1 — take a snapshot every N turns
    "memory_retrieval": true    // OPTIONAL boolean — inject retrieved memories into context
  }
}
```

If the `sbp` object is absent or null, the server MUST behave as a standard
OpenAI-compatible proxy with no session tracking (zero overhead passthrough).

**Model field:** The `model` field is passed through verbatim to the underlying
LLM router. The SBP server MUST NOT restrict or rewrite this field except as
needed for routing. An institution MAY use any model string that their LLM
gateway recognizes. SBP places no constraint on model choice.

### 6.2 Response envelope — HTTP 200

```jsonc
{
  // ... standard OpenAI response fields ...
  "choices": [...],
  "usage": {...},

  "sbp": {                          // always present when request included sbp object
    "session_id":       "uuid",     // REQUIRED — stable session identifier
    "snapshot_id":      "uuid",     // OPTIONAL — ID of the snapshot taken this turn
    "resume_available": false,      // OPTIONAL — true if a suspended session was found
    "resume_prompt":    null,       // OPTIONAL string — suggested prompt to continue
    "last_checkpoint":  "iso",      // OPTIONAL — ISO timestamp of last successful snapshot
    "step_count":       1,          // OPTIONAL integer — turns completed in this session
    "cost_usd":         0.002,      // OPTIONAL float — cost of this turn in USD
    "model_routed_to":  "gpt-4o"   // OPTIONAL string — actual model used (may differ from requested)
  }
}
```

### 6.3 Response envelope — HTTP 202 Resume Available

If a `suspended` session exists for the calling agent and `force_new_session`
is false, the server SHOULD return HTTP 202 instead of processing the request:

```json
{
  "sbp": {
    "session_id":       "uuid",
    "resume_available": true,
    "resume_prompt":    "You were last working on: summarizing the Q3 financial report.",
    "last_checkpoint":  "2026-05-10T14:30:00Z",
    "step_count":       12,
    "snapshot_id":      "uuid"
  }
}
```

The client SHOULD present the resume prompt to the user and, on confirmation,
resend the original request with `"force_new_session": false` and include the
`session_id` as a header or in the `sbp` object to explicitly resume.

---

## 7. L2 — Tether and Resume

L2 adds the core stateful machinery: a session lifecycle, durable checkpoints,
and the WebSocket-based Tether drain.

### 7.1 Session lifecycle

Sessions progress through the following states:

```
     ┌──────────┐
     │   idle   │  ← session created, no activity yet
     └────┬─────┘
          │ first turn received
          ▼
     ┌──────────┐
     │ running  │  ← LLM is producing output
     └────┬─────┘
          │ surface detaches (WebSocket closes)
          ▼
     ┌──────────────┐
     │  suspended   │  ← Tether is active; output queuing
     └────┬─────────┘
          │ surface reattaches (ATTACH_SESSION received)
          ▼
     ┌──────────┐
     │ running  │  ← Tether queue drained; live output resumes
     └────┬─────┘
          │ terminal condition
          ▼
  ┌───────────┐   ┌────────┐
  │ completed │   │ failed │
  └───────────┘   └────────┘
```

Valid state transitions:

| From | To | Trigger |
|---|---|---|
| idle | running | First turn received |
| running | suspended | Surface WebSocket closes |
| suspended | running | Surface sends `ATTACH_SESSION` |
| running | completed | Agent signals task complete |
| running | failed | Unrecoverable error |
| suspended | failed | Timeout or unrecoverable error |

Implementations MUST persist the session state. A server restart MUST NOT
silently drop a session in `running` or `suspended` state.

### 7.2 Snapshot semantics

An SBP L2 server MUST write a snapshot at the following points:

- **pre_action** — immediately before executing any action with external side
  effects (a tool call, a message send). This allows rollback on failure.
- **post_action** — immediately after an action completes successfully. This
  is the primary crash-recovery point.
- **checkpoint** — every `checkpoint_every` turns, as configured in the
  request (default: 1, i.e. every turn).

A snapshot MUST contain at minimum:

```jsonc
{
  "messages":    [...],       // full conversation history at snapshot time
  "current_task": "string",   // OPTIONAL — human-readable description of current task
  "step_count":  12,          // integer turn count
  "model":       "gpt-4o",    // model string at snapshot time
  "created_at":  "iso"        // ISO 8601 timestamp
}
```

Implementations MAY store additional fields. Snapshots MUST be identified by
a UUID `snapshot_id`. Implementations MUST track which snapshot is the latest
for a given session (L2 servers need not retain all historical snapshots, but
MUST be able to retrieve the latest).

On crash recovery, the server MUST resume from the latest `post_action`
snapshot (or the latest `checkpoint` snapshot if no `post_action` exists).

### 7.3 Tether semantics

The **Tether** is the mechanism by which the agent continues producing turns
while no surface is attached.

When a surface disconnects (WebSocket closes or sends `DETACH`):
1. The server MUST signal the session that the surface has detached.
2. The session MUST begin buffering completed output turns into the Tether
   queue rather than discarding them.
3. The Tether queue MUST be durable: it MUST survive server restarts and MUST
   be accessible from any server replica (not stored in local process memory).

When a surface reconnects (sends `ATTACH_SESSION`):
1. The server MUST query the Tether queue for all buffered turns.
2. The server MUST deliver buffered turns through the live WebSocket in
   chronological order before delivering any new turns.
3. The server MUST then clear the Tether queue.
4. The `SESSION_ATTACHED` frame MUST include a `queued_turns` count.

**Replica safety:** The Tether queue MUST NOT be stored in process-local memory.
An implementation that stores the queue in `asyncio.Queue` or equivalent
in-process structures violates this requirement: a reconnect that routes to a
different server replica will drain an empty queue. The reference server's
in-memory backend deliberately violates this constraint (it is single-process
by design) and MUST NOT be used in multi-replica deployments. Production
deployments SHOULD use a durable backend (e.g. Redis, Temporal, or equivalent).

### 7.4 Resume semantics

A resume is a surface reconnecting to an existing `suspended` session. The
surface MUST send an `ATTACH_SESSION` frame (§11.1) with the original
`session_id` and a valid `session_token`. The server MUST:

1. Validate the `session_token`.
2. Transition the session from `suspended` to `running`.
3. Drain the Tether queue (§7.3).
4. Signal the session that the surface is attached (enables live output again).

Resumes are idempotent: if the session is already `running` when
`ATTACH_SESSION` arrives, the server SHOULD send `SESSION_ATTACHED` and then
drain any queued turns (there may be none).

---

## 8. L3 — Roaming

L3 adds portable session state: a session can be exported to a signed token,
transferred across network boundaries, and imported into a new session on any
conformant SBP server — regardless of the original server's LLM choice or
infrastructure.

### 8.1 Roaming Token

A Roaming Token is a compact JWT signed with HMAC-SHA256:

**Header:**
```json
{ "alg": "HS256", "typ": "JWT" }
```

**Payload:**
```jsonc
{
  "sub": "<export_id>",     // UUID — references the stored bundle
  "sid": "<session_id>",    // UUID — source session
  "iat": 1715000000,        // Unix timestamp — issued at
  "exp": 1715086400         // Unix timestamp — expires at (max 7 days from iat)
}
```

The signing secret MUST be server-specific and MUST NOT be shared across
deployments unless cross-deployment token verification is intentionally desired.
Tokens are single-use by default (see §8.3). Implementations MUST verify the
signature and expiry before accepting a token.

Alternative signing algorithms (RS256, ES256) are OPTIONAL in v1.2 and MAY be
supported by implementations that require asymmetric verification (e.g. to
accept tokens signed by a different server).

### 8.2 Bundle envelope

The bundle is stored server-side; the Roaming Token is a reference to it.
A conformant bundle MUST have the following top-level structure:

```jsonc
{
  "sbp_version":    "1.0",        // bundle format version — separate from wire version
  "exported_at":    "iso",        // ISO 8601 export timestamp
  "label":          null,         // OPTIONAL string — human-readable label
  "session": {
    "id":               "uuid",
    "agent_external_id": "string",
    "status":           "suspended",
    "last_task":        "string | null",
    "created_at":       "iso",
    "step_count":       12
  },
  "messages": [
    {
      "role":       "user | assistant | system | tool",
      "content":    "string | null",
      "model_used": "string | null",
      "cost_usd":   0.002,
      "created_at": "iso"
    }
  ],
  "memory": {
    "schema_id": "uri",    // URI identifying the memory schema — see §15.2
    "payload":   {}        // opaque object; structure defined by schema_id
  },
  "state_snapshot": {} ,  // OPTIONAL — latest agent state snapshot (may be null)
  "metadata": {
    "export_id":      "uuid",
    "message_count":  42,
    "total_cost_usd": 0.18
  }
}
```

The `memory.schema_id` field MUST be a URI. The `memory.payload` is opaque to
the protocol; its structure is defined by the schema identified by `schema_id`.
Implementations that do not recognize a `schema_id` MUST import the session
without memory rather than rejecting the import. This ensures that sessions
exported from a SilkBridge deployment (which uses `silkbridge.memory.v1`) can
be imported into any other SBP server, which will simply skip the memory payload.

### 8.3 Export

`POST /v1/sbp/sessions/{session_id}/export`

Request:
```json
{
  "ttl_seconds": 86400,
  "label": "Tokyo trip planning — handoff to mobile"
}
```

Response (HTTP 201):
```json
{
  "export_id":     "uuid",
  "roaming_token": "eyJ...",
  "expires_at":    "iso",
  "bundle_hash":   "sha256hex",
  "message_count": 42,
  "label":         "Tokyo trip planning — handoff to mobile"
}
```

`ttl_seconds` MUST be in the range [60, 604800] (1 minute to 7 days). Servers
MAY enforce a shorter maximum.

### 8.4 Import

`POST /v1/sbp/sessions/import`

Request:
```json
{
  "roaming_token":   "eyJ...",
  "target_agent_id": null,
  "allow_reuse":     false
}
```

The server MUST:
1. Verify the token's HMAC-SHA256 signature.
2. Check that the token has not expired.
3. Check that the token has not been consumed (unless `allow_reuse: true`).
4. Replay messages in chronological order into a new session.
5. Restore the memory payload if the `schema_id` is recognized; skip otherwise.
6. Restore the state snapshot if present.
7. Inject a system message noting the import provenance.
8. Mark the token as consumed.

Response (HTTP 201): the new `session_id`, `session_token`, `step_count`,
`message_count`, and `agent_id`.

If `allow_reuse: true`, the import creates a Fork (§8.6) from the bundle
rather than consuming the token. Multiple imports with `allow_reuse: true`
produce independent forks that share all history through the export point.

### 8.5 Inspect

`GET /v1/sbp/token/{roaming_token}`

Returns export metadata without consuming the token: `export_id`, `session_id`,
`expires_at`, `imported_at` (null if unconsumed), `label`, `message_count`.
Useful for UI previews before an import.

### 8.6 Handoff

`POST /v1/sbp/sessions/{session_id}/handoff`

An atomic operation:
1. Exports the source session.
2. Imports the bundle into a new session under `to_agent_id`.
3. Injects a bridge message (`handoff_message`) at the start of the new session.
4. Suspends the source session.

Response (HTTP 201): includes the new session's `session_id`, `session_token`,
and the `to_agent_id` that received it. The handoff is recorded in lineage (§8.8).

### 8.7 Fork

`POST /v1/sbp/sessions/{session_id}/fork`

Creates an independent copy of the current session at the latest checkpoint.
Both the origin and the fork are fully independent from the fork point forward.
Uses: A/B exploration, counterfactual testing, parallel work streams.

Response (HTTP 201): includes the fork's `session_id`, `session_token`, and
`fork_label`.

### 8.8 Lineage

`GET /v1/sbp/sessions/{session_id}/lineage`

Returns the full family tree of the session:
- `exports` — all export records (export_id, expires_at, imported_at, import_session_id)
- `outgoing_handoffs` — sessions this session handed off to
- `incoming_handoffs` — sessions that handed off to this session
- `forks` — sessions forked from this session
- `origin` — if this session is itself a fork, the origin session

---

## 9. L4 — Surface Negotiation

L4 allows surfaces to declare their capabilities at attach time. The server
MAY use this information to adapt its output. Servers MUST tolerate unknown
values in any SurfaceContext field.

### 9.1 SurfaceContext schema

The `SurfaceContext` object is sent inside the `ATTACH_SESSION` WebSocket frame:

```jsonc
{
  "device_type":       "mobile",     // REQUIRED — see §9.2
  "max_output_tokens": 500,          // OPTIONAL integer — output length hint; null = no limit
  "ui_capabilities":   ["markdown"], // OPTIONAL array of strings — see §9.3
  "locale":            "en-US",      // OPTIONAL string — BCP-47 locale code
  "surface_id":        "uuid",       // OPTIONAL string — stable device fingerprint
  "mcp_tools":         ["camera"]    // OPTIONAL array of strings — local MCP tool names; see §10
}
```

### 9.2 Well-known device types

| `device_type` | Description |
|---|---|
| `"mobile"` | Smartphone (iOS, Android) |
| `"desktop"` | Laptop or desktop browser |
| `"iot"` | IoT device (e.g. Apple Watch, smart display) |
| `"browser"` | Web browser on any device class |
| `"voice"` | Voice-only interface (e.g. AirPods, smart speaker) |
| `"unknown"` | Device type not known or not disclosed |

Implementations MUST accept any string value for `device_type` (for
forward-compatibility). Unknown values SHOULD be treated as `"unknown"`.

### 9.3 Well-known UI capabilities

| Capability string | Meaning |
|---|---|
| `"markdown"` | Surface can render Markdown (bold, lists, headings, etc.) |
| `"tables"` | Surface can render tabular data |
| `"images"` | Surface can display images |
| `"audio"` | Surface has audio output (text-to-speech is possible) |
| `"streaming"` | Surface prefers streaming (TURN_CHUNK) over batch (TETHER_TURN) |

Implementations MUST accept unknown capability strings and ignore them.

### 9.4 Server adaptation

Servers SHOULD use the `SurfaceContext` to adapt their output:
- Respect `max_output_tokens` when generating or summarizing responses.
- Avoid Markdown if `"markdown"` is absent from `ui_capabilities`.
- Prefer audio-friendly prose if `"audio"` is present.
- Use the `locale` for language selection and date/number formatting.

Servers MUST NOT fail or degrade in functionality for surfaces that send
minimal or empty `SurfaceContext`. The default behavior (no adaptation) MUST
be a valid, complete experience.

---

## 10. L5 — Surface MCP Bridge

L5 turns the SBP WebSocket into a bidirectional MCP bridge. Surfaces declare
local MCP tools in `SurfaceContext.mcp_tools`; the gateway can then call those
tools as if they were server-side MCP tools. From the LLM's perspective, the
tool call is no different from any other tool call.

This is the "Northbound MCP" capability: the surface is simultaneously an SBP
client (receiving turns) and an MCP server (executing tool calls).

### 10.1 Tool declaration

A surface declares its tools in the `ATTACH_SESSION` frame's
`surface_context.mcp_tools` array. Each entry is a tool name string (e.g.
`"camera"`, `"gps"`, `"contacts"`).

The gateway SHOULD inject corresponding tool schemas into the LLM's tool
list so the model knows these tools are available. In v1.2 the schema format
is implementation-defined; a future spec version MAY define a standard tool
schema negotiation frame.

### 10.2 TOOL_CALL frame

When the agent requests a surface tool call, the gateway sends a `TOOL_CALL`
frame to the attached surface:

```json
{
  "type":       "TOOL_CALL",
  "call_id":    "uuid",
  "tool_name":  "camera",
  "tool_input": { "mode": "photo", "facing": "back" }
}
```

`call_id` MUST be unique per session for the lifetime of the session. Multiple
tool calls MAY be in-flight simultaneously; they are correlated by `call_id`.

### 10.3 TOOL_RESULT frame

The surface executes the tool and replies with a `TOOL_RESULT` frame:

```jsonc
{
  "type":    "TOOL_RESULT",
  "call_id": "uuid",         // matches the TOOL_CALL call_id
  "result":  { ... },        // tool output; structure is tool-specific
  "error":   null            // string if the tool failed; null on success
}
```

The gateway MUST match the `call_id` to the pending `TOOL_CALL` and deliver
the result to the LLM.

### 10.4 Timeout and cancellation

The gateway SHOULD apply a default timeout of 30 seconds per tool call.
If the surface does not respond within the timeout, the gateway MUST treat
the call as failed (equivalent to `"error": "timeout"`).

If the surface disconnects while a tool call is in-flight, the gateway MUST
treat all in-flight calls for that session as cancelled.

### 10.5 Tool authorization

In v1.2, a surface is implicitly authorized to execute tools it declared in
`mcp_tools`. The gateway SHOULD NOT route a `TOOL_CALL` to a surface for a
tool not present in the surface's declared `mcp_tools` list.

Future spec versions MAY define per-tool authorization policies.

---

## 11. WebSocket Frame Catalog

All frames are JSON objects with a `"type"` string field. Unknown frame types
MUST be ignored (forward-compatible extension point).

The first frame from the client MUST be `ATTACH_SESSION`. The server MUST
close the connection (code 1003) if any other frame type arrives first.

### 11.1 Client → Server frames

#### `ATTACH_SESSION`
```jsonc
{
  "type":            "ATTACH_SESSION",
  "session_id":      "uuid",      // REQUIRED — must match URL path parameter
  "session_token":   "string",    // REQUIRED — credentials for this session
  "surface_context": { ... }      // OPTIONAL — SurfaceContext (§9.1)
}
```

#### `DETACH`
```json
{ "type": "DETACH" }
```
Graceful disconnect. The server MUST activate the Tether.

#### `TOOL_RESULT`
```jsonc
{
  "type":    "TOOL_RESULT",
  "call_id": "uuid",
  "result":  { ... },
  "error":   null
}
```

#### `PONG`
```json
{ "type": "PONG" }
```
Reply to a `PING`. No other action required.

### 11.2 Server → Client frames

#### `SESSION_ATTACHED`
```jsonc
{
  "type":                  "SESSION_ATTACHED",
  "session_id":            "uuid",
  "surface_id":            "uuid | null",
  "device_type":           "mobile",
  "queued_turns":          3,            // number of Tether turns about to be drained
  "mcp_tools_registered":  ["camera"],   // L5: tools the gateway accepted
  "sbp_version":           "1.2",
  "sbp_level":             "L5"          // OPTIONAL — server's conformance level
}
```

#### `SESSION_NOT_FOUND`
```json
{ "type": "SESSION_NOT_FOUND", "detail": "No session with ID abc123" }
```
Sent when the session_id is unknown. Server closes after sending.

#### `FORBIDDEN`
```json
{ "type": "FORBIDDEN", "detail": "session_token invalid or expired" }
```
Sent when the session_token fails validation. Server closes after sending.

#### `PROTOCOL_ERROR`
```json
{ "type": "PROTOCOL_ERROR", "detail": "Expected ATTACH_SESSION as first frame" }
```
Sent on protocol violations. Server closes after sending.

#### `TETHER_TURN`
```jsonc
{
  "type":        "TETHER_TURN",
  "turn_index":  0,              // zero-based position in the drain sequence
  "role":        "assistant",
  "content":     "Here is what I found while you were away...",
  "model_used":  "gpt-4o",
  "created_at":  "iso"
}
```
Delivers a buffered turn from the Tether queue during drain.

#### `TURN_CHUNK`
```jsonc
{
  "type":     "TURN_CHUNK",
  "chunk_id": "uuid",
  "delta":    "partial text content"
}
```
Streaming output chunk from the Contextual Translation Pipeline or LLM stream.

#### `TURN_COMPLETE`
```json
{ "type": "TURN_COMPLETE", "chunk_id": "uuid" }
```
Signals that the stream for `chunk_id` is finished.

#### `TOOL_CALL`
```jsonc
{
  "type":       "TOOL_CALL",
  "call_id":    "uuid",
  "tool_name":  "camera",
  "tool_input": { "mode": "photo" }
}
```

#### `PING`
```json
{ "type": "PING" }
```
Keepalive. Client MUST reply with `PONG` within 10 seconds or the server MAY
close the connection.

---

## 12. Error Model

### 12.1 HTTP error responses

All REST endpoints return errors as JSON:

```json
{
  "error": {
    "code":    "SBP_SESSION_NOT_FOUND",
    "message": "Session 'abc123' not found",
    "detail":  "..."
  }
}
```

Reserved SBP error code range: `SBP_` prefix.

| Code | HTTP Status | Meaning |
|---|---|---|
| `SBP_SESSION_NOT_FOUND` | 404 | Session does not exist |
| `SBP_TOKEN_EXPIRED` | 410 | Roaming Token has expired |
| `SBP_TOKEN_CONSUMED` | 410 | Roaming Token has already been imported |
| `SBP_TOKEN_INVALID` | 422 | Token signature verification failed |
| `SBP_TOKEN_INTEGRITY` | 422 | Bundle hash mismatch |
| `SBP_INVALID_UUID` | 422 | Path parameter is not a valid UUID |
| `SBP_SESSION_CONFLICT` | 409 | Operation conflicts with current session state |
| `SBP_INTERNAL` | 500 | Unrecoverable server error |

### 12.2 WebSocket close codes

| Code | Meaning |
|---|---|
| 1000 | Normal closure |
| 1003 | Protocol error (bad frame type) |
| 4003 | Forbidden (bad session_token) |
| 4004 | Session not found |

---

## 13. Security Considerations

### 13.1 Roaming Token storage

Roaming Tokens are compact JWTs signed with HMAC-SHA256. The signing secret
(`jwt_secret`) MUST be:
- At least 256 bits of entropy.
- Stored outside of version control (environment variable or secrets manager).
- Rotated periodically. Token rotation invalidates all outstanding tokens.

The default token TTL is 24 hours; the maximum is 7 days. Tokens MUST be
transmitted only over TLS.

### 13.2 Bundle integrity

Each bundle is hashed with SHA-256 at export time. The gateway MUST verify the
hash on import. If the hash does not match the bundle, the import MUST be
rejected with `SBP_TOKEN_INTEGRITY`.

### 13.3 Snapshot encryption at rest

This spec does not mandate encryption of snapshots or bundles at rest.
Implementations that store personal data in snapshots SHOULD apply encryption
at rest and SHOULD consider column-level encryption for message content that
may contain PII.

### 13.4 Replay attacks

Roaming Tokens are single-use by default. Implementations MUST track consumed
token IDs and reject re-use (returning `SBP_TOKEN_CONSUMED`) unless the
caller explicitly passes `allow_reuse: true`, which creates a Fork rather than
a standard import.

### 13.5 Surface impersonation

The `session_token` in `ATTACH_SESSION` is the sole authentication mechanism
for surfaces in v1.2. Implementations in high-security environments SHOULD add
additional binding such as:
- TLS client certificates (mTLS) between the surface and the gateway.
- Short-lived surface tokens bound to a device fingerprint (`surface_id`).

### 13.6 Surface-tool authorization

The gateway SHOULD only invoke tools that the surface declared in `mcp_tools`
at attach time. Implementations SHOULD validate the declared tool list against
an allowlist. Surface tools have access to device-local capabilities (camera,
contacts, GPS) and MUST be treated with the same caution as any privileged API.

---

## 14. MCP Interoperability

SBP and MCP compose at two levels:

### 14.1 Southbound MCP (server-side tools)

The agent gateway acts as an MCP client: it calls server-side MCP tools
(databases, APIs, file systems) via MCP's standard `tools/call` protocol. This
is unaffected by SBP. SBP carries the agent's state context; MCP carries the
tool calls. Both run in parallel.

### 14.2 Northbound MCP (surface-side tools via SBP Bridge)

When a surface declares `mcp_tools` in its `SurfaceContext`:
1. The surface becomes an MCP server, reachable through the SBP WebSocket.
2. The gateway injects tool schemas for surface tools into the LLM's system
   prompt or tool list.
3. When the LLM requests a surface tool, the gateway translates the MCP
   `tools/call` into a `TOOL_CALL` WebSocket frame and delivers it to the
   surface.
4. The surface executes the tool (taking a photo, reading GPS coordinates,
   fetching contacts) and sends a `TOOL_RESULT` frame.
5. The gateway delivers the result back to the LLM as an MCP tool response.

The surface need not implement the full MCP protocol — the gateway handles the
MCP layer. The surface only needs to handle `TOOL_CALL` and send `TOOL_RESULT`.

### 14.3 Model-agnostic tool integration

Because SBP is model-agnostic, the tool injection in §14.2 MUST be compatible
with any LLM that the gateway routes to. Implementations that support Northbound
MCP MUST format tool schemas in a way that is compatible with their LLM router's
tool-calling conventions. The protocol does not specify which LLM is used; the
tool call semantics are an implementation concern.

---

## 15. IANA and Registry Considerations

### 15.1 The `sbp` namespace

The `sbp` top-level key in OpenAI-compatible request and response bodies is
reserved for the State Bridge Protocol. Implementations SHOULD NOT use this key
for non-SBP purposes.

### 15.2 Memory schema URI registry

The `memory.schema_id` field accepts a URI. Known schema URIs are listed below.
Anyone may register a URI by opening a PR to add a row to this table.

| URI | Owner | Description |
|---|---|---|
| `silkbridge.memory.v1` | SilkBridge (MARGNE-AI) | Episodic, semantic, and procedural memory. Implementation-defined payload; not part of the SBP open spec. |

Implementations that encounter an unrecognized `schema_id` MUST import the
session without the memory payload.

### 15.3 Well-known surface device types

Additions to the `device_type` registry require a PR to this spec. The current
registered values are: `mobile`, `desktop`, `iot`, `browser`, `voice`, `unknown`.

### 15.4 Well-known UI capabilities

Additions to the `ui_capabilities` registry require a PR to this spec.
Current registered values: `markdown`, `tables`, `images`, `audio`, `streaming`.

---

## 16. References

- **[RFC 2119]** Bradner, S., "Key words for use in RFCs to Indicate Requirement Levels", March 1997. https://www.rfc-editor.org/rfc/rfc2119
- **[RFC 7519]** Jones, M., et al., "JSON Web Token (JWT)", May 2015. https://www.rfc-editor.org/rfc/rfc7519
- **[RFC 8259]** Bray, T., "The JavaScript Object Notation (JSON) Data Interchange Format", December 2017. https://www.rfc-editor.org/rfc/rfc8259
- **[MCP]** Anthropic, "Model Context Protocol Specification". https://spec.modelcontextprotocol.io/
- **[OpenAI Chat Completions API]** https://platform.openai.com/docs/api-reference/chat

---

## Appendix A — JSON Schemas

Full JSON Schema definitions for all SBP wire structures are in
[`../schemas/`](../schemas/):

- [`completions-request.schema.json`](../schemas/completions-request.schema.json)
- [`completions-response.schema.json`](../schemas/completions-response.schema.json)
- [`surface-context.schema.json`](../schemas/surface-context.schema.json)
- [`ws-frames.schema.json`](../schemas/ws-frames.schema.json)
- [`roaming-token.schema.json`](../schemas/roaming-token.schema.json)
- [`roaming-bundle.schema.json`](../schemas/roaming-bundle.schema.json)
- [`lineage.schema.json`](../schemas/lineage.schema.json)

---

## Appendix B — Worked Examples

Wire-level examples for each conformance level are in [`../examples/`](../examples/):

- [`01-l1-stateful-proxy.http`](../examples/01-l1-stateful-proxy.http) — L1 request/response
- [`02-l2-resume.http`](../examples/02-l2-resume.http) — L2 HTTP 202 resume
- [`03-l3-export.http`](../examples/03-l3-export.http) — L3 session export
- [`04-l3-import.http`](../examples/04-l3-import.http) — L3 session import
- [`05-l3-handoff.http`](../examples/05-l3-handoff.http) — L3 handoff
- [`06-l3-fork.http`](../examples/06-l3-fork.http) — L3 fork
- [`07-l4-attach-with-surface.json`](../examples/07-l4-attach-with-surface.json) — L4 ATTACH_SESSION frame
- [`08-l5-tool-call.json`](../examples/08-l5-tool-call.json) — L5 TOOL_CALL frame
- [`09-l5-tool-result.json`](../examples/09-l5-tool-result.json) — L5 TOOL_RESULT frame

---

## Appendix C — Change History

| Version | Date | Summary |
|---|---|---|
| **1.2** | 2026-05-10 | Initial public release. All five capabilities (L1–L5) specified. Reference server and TS client shipped. |
| 1.1 | *(internal)* | Lineage tracking added; bundle envelope finalized. |
| 1.0 | *(internal)* | First end-to-end Tether + Resume implementation at MARGNE-AI. |
