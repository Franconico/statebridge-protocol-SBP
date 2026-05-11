# SBP Conformance Levels

An SBP implementation declares a conformance level from L1 to L6. Levels are **cumulative** — an L3 implementation also satisfies L1 and L2.

---

## Overview

| Level | Name | Description |
|-------|------|-------------|
| **L1** | Stateful Proxy | Persistent conversation + REST completions |
| **L2** | Tether + Resume | Durable turn buffering + WebSocket attach/detach |
| **L3** | Roaming | Content-addressed session bundles + import/export |
| **L4** | Surface Negotiation | Device-aware ATTACH_SESSION handshake |
| **L5** | MCP Bridge | Bi-directional surface-local tool invocation |
| **L6** | Gateway Federation | Decentralised peer discovery + cross-gateway roaming |
| **L7** | Direct Data Plane *(reserved, v0.2)* | Optional WebRTC surface↔surface streaming |

---

## L1 — Stateful Proxy

**The gateway maintains persistent agent sessions.**

### Required

- `POST /v1/sessions` — create a session with a `session_token`
- `POST /v1/completions` (or equivalent) — run a turn; persist messages
- `GET /v1/sessions/{id}` — retrieve session status and step count
- Messages MUST be persisted across gateway restarts
- Agent identity MUST be stable across calls

### Optional

- Streaming completions
- Memory (episodic, semantic, procedural)
- Tool execution

### What is NOT required

- WebSocket
- Tether buffering
- Roaming

---

## L2 — Tether + Resume

**The gateway buffers agent output when the surface is offline and delivers it on reconnect.**

### Required (in addition to L1)

- `wss://<host>/v1/sbp/ws/{session_id}` — WebSocket endpoint
- `ATTACH_SESSION` / `SESSION_ATTACHED` handshake
- `TETHER_TURN` delivery on re-attach
- `TURN_CHUNK` + `TURN_COMPLETE` for live streaming
- `DETACH` and unclean-disconnect handling
- The Tether backend MUST survive gateway process restart (durable storage — SQLite, PostgreSQL, Redis Streams, Temporal, or equivalent)
- `tether_turns_pending` count in `SESSION_ATTACHED`

### Tether backend options

Any of the following satisfy L2 durability:

| Backend | Notes |
|---------|-------|
| SQLite | Zero external dependencies. File-based durability. Single-node only. |
| PostgreSQL | Production-grade. Multi-node read replicas. |
| Redis Streams | Multi-replica delivery, configurable AOF persistence. |
| Temporal workflow state | Enterprise. 30-day Tether with guaranteed activity delivery. |
| Cloudflare Durable Objects | Edge-native, globally distributed, single-Object-per-session. |

---

## L3 — Roaming

**Sessions are portable as content-addressed bundles that any compliant gateway can import.**

### Required (in addition to L2)

- `POST /v1/sbp/sessions/{id}/export` — returns `{ roaming_token, bundle_cid, ... }`
- `POST /v1/sbp/sessions/import` — accepts `roaming_token`, creates new session
- Bundle MUST include: `sbp_version`, `bundle_cid`, `session`, `messages`, `memory`, `metadata`
- `bundle_cid` MUST equal `sha256(json.dumps(bundle, sort_keys=True).encode('utf-8'))` before the field is inserted into the bundle
- Importing gateway MUST verify `bundle_cid` on receipt
- Default token consumption: single-use (one import per export)
- `allow_reuse: true` MUST produce a fork (both sessions coexist independently)

### Recommended

- `POST /v1/sbp/sessions/{id}/handoff` — transfer to another agent
- `POST /v1/sbp/sessions/{id}/fork` — branch at current checkpoint
- `GET /v1/sbp/sessions/{id}/lineage` — full family tree (exports, handoffs, forks)

---

## L4 — Surface Negotiation

**The gateway adapts its output to the surface's device type and capabilities.**

### Required (in addition to L3)

- `ATTACH_SESSION` MUST accept a `surface` field (SurfaceContext)
- Gateway MUST store `SurfaceContext` for the duration of the attachment
- Gateway MUST pass `device_type` and `max_output_tokens` to output generation
- Gateway MUST handle `surface: null` gracefully (treat as `device_type: "unknown"`)

### SurfaceContext fields

| Field | Type | Required |
|-------|------|----------|
| `device_type` | `mobile \| desktop \| iot \| browser \| voice \| unknown` | Yes |
| `max_output_tokens` | `int \| null` | No |
| `ui_capabilities` | `string[]` | No |
| `locale` | `string` (BCP-47) | No |
| `surface_id` | `string \| null` | No |
| `mcp_tools` | `string[]` | No |

### Recommended

- Contextual Translation Pipeline (CTP): second LLM pass to reformat output for mobile/IoT
- Streaming CTP output as `TURN_CHUNK` frames (not blocking until full)

---

## L5 — MCP Bridge

**Agents can invoke tools that run locally on the surface.**

### Required (in addition to L4)

- Gateway MUST register surface-declared `mcp_tools` as callable tools in the agent's tool schema
- Gateway MUST emit `TOOL_CALL` frames and await `TOOL_RESULT` responses
- `call_id` MUST be unique per invocation (UUID)
- Timeout MUST be enforced (RECOMMENDED: 30 seconds)
- On timeout or disconnection, gateway MUST return an error tool result to the agent (not deadlock)
- Surface MUST respond with `TOOL_RESULT` matching the `call_id`

### Multi-replica deployments

- In single-replica: in-process Future rendezvous is acceptable
- In multi-replica: cross-process pub/sub (Redis pub/sub, Temporal signal, etc.) MUST be used to route TOOL_RESULT to the correct pod

---

## L6 — Gateway Federation (Optional)

**Independent gateways discover each other and exchange bundles by CID.**

### Two roles

An L6 node operates in one of two roles (or both):

- **Gateway**: hosts live sessions, serves bundles by CID. The default.
- **Tracker**: indexes which Gateway holds which `bundle_cid`. Optional, no session content.

A deployment MAY combine both roles in a single process. Public SBP infrastructure
SHOULD separate them so Trackers can be operated cheaply at scale without privileged
access to session content.

### Required (in addition to L5)

- `GET /.well-known/sbp` — discovery endpoint including a `role` field
- `GET /v1/sbp/bundles/{bundle_cid}` — bundle resolution by CID (Gateways only)
- Bundle resolution MUST verify `bundle_cid` before returning
- Federation token (signed JWT or mutual TLS) MUST be required for bundle resolution
- Trackers MUST NOT proxy bundle content; they return only references
- Trackers MUST sign their registry responses with the same key advertised in `/.well-known/sbp`

### Discovery endpoint response

```json
{
  "sbp_version": "1.2",
  "gateway_id": "<string>",
  "federation": true,
  "public_key": "<base64-DER>",
  "endpoints": {
    "ws": "wss://<host>/v1/sbp/ws/{session_id}",
    "bundle": "https://<host>/v1/sbp/bundles/{bundle_cid}",
    "import": "https://<host>/v1/sbp/sessions/import"
  }
}
```

### Recommended

- Static peer list in gateway config
- DNS SRV peer discovery (`_sbp._tcp.<domain>`)
- Automatic session migration: surface connects to nearest L6 gateway; gateway fetches bundle from origin peer transparently

---

## L7 — Direct Data Plane (Reserved, v0.2)

**Optional WebRTC surface↔surface streaming with Gateway-mediated signalling.**

L7 is **reserved** in SBP v1.2 and not normative. It will be specified separately
once a reference implementation demonstrates its operational tradeoffs.

### Motivating use case

Two surfaces on the same local network (a phone and a watch, a desktop and a tablet)
exchanging live agent output without round-tripping through the cloud Gateway. The
Gateway remains the source of truth for the session bundle and Tether, but acts only
as a signalling server during the WebRTC handshake.

### Why it's reserved

- WebRTC requires STUN/TURN infrastructure that inflates minimum viable implementations
- NAT traversal failure modes are subtle and add a long error surface
- The use case is real but narrow — most deployments do not need it

Implementations that ship a WebRTC data plane MAY self-describe as "L7-experimental"
but MUST NOT claim L7 conformance until the specification is finalised.

---

## Self-certification

To claim a conformance level, run the SBP conformance test suite against your server URL:

```bash
npx sbp-conformance --url https://your-gateway.example.com --level L5
```

The test suite is available at: `statebridge-protocol/sbp-conformance`

---

## Reference Implementations

| Implementation | Level | Backend | Notes |
|---------------|-------|---------|-------|
| `sbp-server` (Python, SQLite) | L5 | SQLite | Default. Zero external dependencies. |
| `sbp-server` (Python, PostgreSQL) | L5 | PostgreSQL + Redis | Production OSS. |
| SilkBridge Cloud | L6 | Temporal + PostgreSQL | Enterprise SaaS. |

---

*SBP Conformance Levels — v1.2 — © 2026 Silkbridge, Inc. — Apache-2.0*
