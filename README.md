# State Bridge Protocol (SBP)

> **The Northbound protocol for AI agents — durable state across disconnects, devices, and time.**

[![Spec v1.2](https://img.shields.io/badge/spec-v1.2-blue.svg)](spec/SPEC.md)
[![License: Apache 2.0](https://img.shields.io/badge/license-Apache--2.0-green.svg)](LICENSE)
[![Reference Server: Python](https://img.shields.io/badge/reference%20server-Python-yellow.svg)](reference/server-python/)
[![Reference Client: TypeScript](https://img.shields.io/badge/reference%20client-TypeScript-yellow.svg)](reference/client-typescript/)

---

## The problem

Today's AI agents die when the WebSocket dies. OpenAI, Anthropic, and MCP are
**stateless** — every reconnect resets the conversation. Every "agent platform"
reinvents session management ad hoc, and none of it survives the user driving
home, switching to their watch, or handing the task to a colleague.

**SBP fixes this.** It's the open standard for the state layer between an agent
and the human it serves: durable sessions, device handoff, surface adaptation,
a bidirectional MCP bridge — and now **federated gateways** so no single server
is a single point of failure.

## Northbound vs Southbound — SBP and MCP are complementary

```
         ┌──────────────┐   ┌──────────────┐   ┌──────────────┐
         │ Gateway NYC  │   │ Gateway FRA  │   │ Gateway SIN  │
         └──────┬───────┘   └──────┬───────┘   └──────┬───────┘
                │                  │   ⇄ L6 Federation  │
                └──────────────────┴───────────────────┘
                                   │
                            ⇅  SBP (Northbound)
                                   │
         ┌─────────────────────────┴────────────────────────┐
         │  Apple Watch · Phone · Browser · Voice · IoT …  │
         └──────────────────────────────────────────────────┘

                                   │
                            ⇅  MCP (Southbound)
                                   │
         ┌─────────────────────────┴────────────────────────┐
         │        Databases · APIs · Files · Tools          │
         └──────────────────────────────────────────────────┘
```

|                   | **MCP** (Southbound)                | **SBP** (Northbound)                       |
| ----------------- | ----------------------------------- | ------------------------------------------ |
| Connects agent to | Tools, databases, APIs              | Humans, devices, surfaces                  |
| Stateful?         | No (per-call)                       | **Yes** (sessions survive disconnects)     |
| Scope             | "Give the agent hands"              | "Give the agent a soul that persists"      |
| Typical transport | stdio, HTTP+SSE                     | HTTP + WebSocket                           |
| LLM-agnostic?     | Yes                                 | **Yes** — any OpenAI-compatible model      |
| Server-agnostic?  | Yes (stdio, HTTP)                   | **Yes** — swap backend implementations freely |
| Created by        | Anthropic                           | The State Bridge community (open standard) |

**SBP carries MCP, it does not replace it.** A surface (phone, watch) can declare
its own MCP tools (camera, GPS, contacts) at attach-time, and the agent can
invoke them through SBP's bidirectional bridge. *MCP gives the agent hands;
SBP gives the agent a soul that survives the drive home.*

## Model-agnostic. Server-agnostic. Federation-ready.

SBP places **no requirements** on which LLM or which server infrastructure you
use. Every institution keeps the freedom to select and change both independently:

```
  ┌────────────────────────────────────────────────────────────────┐
  │                    SBP Request Envelope                        │
  │  model: "claude-opus-4"  ← change to any model at any time    │
  │  model: "gpt-4o"                                               │
  │  model: "llama-4-scout"        ← local, open-source, on-prem  │
  │  model: "deepseek-v3"          ← change provider seamlessly   │
  └────────────────────────────────────────────────────────────────┘

  ┌────────────────────────────────────────────────────────────────┐
  │                    SBP Tether Backend                          │
  │  SQLite (default)   ← zero deps, single-node, file-based      │
  │  PostgreSQL + Redis ← multi-replica, production OSS           │
  │  Temporal           ← enterprise durable execution            │
  │  Cloudflare DO      ← edge-native, globally distributed       │
  │  your-own           ← implement the 4-method interface        │
  └────────────────────────────────────────────────────────────────┘
```

**Why this matters:**
- A hospital can run SBP with a local Llama model on-premises — no cloud calls,
  no data leaving the building.
- A startup can switch from GPT-4o to Claude mid-session by changing one field —
  sessions survive the model swap.
- An enterprise can move from SQLite to PostgreSQL to Temporal without changing
  application code or surface clients.
- No vendor can "own" SBP by locking in an LLM or an infra tier. The protocol
  is defined by the wire format, not the model or the backend.

## The six capabilities

| # | Capability        | What it does                                                        |
|---|-------------------|---------------------------------------------------------------------|
| 1 | **Tether**        | Server keeps producing turns even when no surface is attached       |
| 2 | **Resume**        | Same client reconnects after a disconnect; missed turns are drained |
| 3 | **Roaming**       | Export full session state → portable signed token → import anywhere |
| 4 | **Surface**       | Surfaces declare device type, screen size, capabilities at attach   |
| 5 | **MCP Bridge**    | Surfaces expose local MCP tools the agent can call over WebSocket   |
| 6 | **Federation**    | Independent gateways discover each other and exchange bundles by CID |

## Conformance levels

Pick how deep you implement. Levels are cumulative.

| Level | Name | Adds | Effort |
|-------|------|------|--------|
| **L1** | Stateful Proxy | `sbp` namespace on OpenAI-compatible completions | An afternoon |
| **L2** | Tether + Resume | Durable turn queue; WebSocket attach/drain | A week |
| **L3** | Roaming | Export/import/handoff/fork/lineage; content-addressed bundles | Two weeks |
| **L4** | Surface Negotiation | `SurfaceContext` at attach; device-aware output | Days on top of L3 |
| **L5** | MCP Bridge | Bidirectional `TOOL_CALL`/`TOOL_RESULT` over WebSocket | A week on top of L4 |
| **L6** | Gateway Federation | `/.well-known/sbp` discovery; cross-gateway bundle resolution by SHA-256 CID | A week on top of L5 |
| **L7** *(reserved)* | Direct Data Plane | WebRTC surface↔surface streaming (v0.2, not normative) | TBD |

See [`docs/reference/conformance-levels.md`](docs/reference/conformance-levels.md)
for the full normative checklists and [`docs/concepts/federation.md`](docs/concepts/federation.md)
for the Silk Road federation model.

## Quickstart

```bash
# 1. Install + start the L5-conformant reference server (SQLite backend, zero deps)
pip install sbp-server-reference          # (will be on PyPI for v0.1 launch)
sbp-server start --port 8080

# 2. L1 — stateful proxy: send a chat completion with the `sbp` namespace
curl -X POST http://localhost:8080/v1/chat/completions \
  -H 'Content-Type: application/json' \
  -d '{
    "model": "gpt-4o",
    "messages": [{"role": "user", "content": "Plan a 3-day trip to Tokyo"}],
    "sbp": { "checkpoint_every": 1 }
  }'
# → returns sbp.session_id + sbp.snapshot_id you can resume from

# 3. L4/L5 — attach a surface via WebSocket
wscat -c ws://localhost:8080/v1/sbp/ws/<session_id> \
  -x '{"type":"ATTACH_SESSION","session_id":"<id>","session_token":"<tok>",
       "surface_context":{"device_type":"mobile","ui_capabilities":["markdown"],
                          "mcp_tools":["camera"]}}'
# → SESSION_ATTACHED, then any buffered Tether turns drain through the live socket

# 4. L6 — federation: see who's running SBP
curl https://your-gateway.example.com/.well-known/sbp
# → { "sbp_version": "1.2", "gateway_id": "...", "federation": true, ... }
```

Full walkthrough: [`docs/getting-started.md`](docs/getting-started.md).

## Hosted & enterprise

Run SBP yourself with the Apache-2.0 reference server, or skip the ops:

- **[SilkBridge Enterprise](https://silkbridge.io/enterprise)** — production-grade
  Temporal backend (durable Tether across pod restarts, scaling events, 30-day
  disconnects), Contextual Translation Pipeline (Gemini-Flash adaptive output),
  HITL workflows, sovereign VPC, full observability.
- **SilkBridge Cloud** *(coming soon)* — SBP-as-a-service. Point your agent at
  `api.silkbridge.cloud`, attach your surface, get L5 instantly. No servers to run.

### OSS reference vs SilkBridge — feature matrix

| Layer | OSS reference (free, Apache-2.0) | SilkBridge Enterprise / Cloud |
|---|---|---|
| Protocol spec | Full SBP v1.2 | Same — it's the open standard |
| Reference server | **L5**, SQLite (zero deps, single-node) or PostgreSQL+Redis (multi-replica) | **L6**, **Temporal backend** — durable Tether across pod restarts, scaling events, 30-day disconnects with guaranteed delivery |
| Gateway federation | Spec-compliant `/.well-known/sbp` + bundle resolution; static peer list | Managed gateway mesh — automatic cross-region session migration, SLA-backed availability |
| Surface translation | Frame protocol only (`TURN_CHUNK` descriptor) | **Contextual Translation Pipeline** — Gemini-Flash streaming adaptation (4k-token report → 2-sentence watch glance) |
| Surface MCP bridge | Wire protocol (`TOOL_CALL`/`TOOL_RESULT` frames, Future rendezvous) | **LLM-side connector** — dynamic injection of surface-declared tools into the LLM's `tool_calls`; per-tool authz |
| Memory | Bundle envelope + `schema_id` URI registry | `silkbridge.memory.v1` — episodic / semantic / procedural consolidation |
| Observability | None (logs to stdout) | Braintrust + LangSmith tracing, cost MVs, forensic trees |
| HITL | None | Full approval workflow with reviewer routing |
| Multi-tenancy | None | Sovereign VPC isolation |
| Operations | You run it | **SilkBridge Cloud** *(coming soon)* — managed, SLA-backed |

The protocol is free; the operational trust is what SilkBridge sells. Any
implementer can build an L6 server from this spec — but you'd be building
Twilio's stack from scratch.

## Repository map

```
statebridge-protocol/sbp/
├── spec/
│   ├── SPEC.md                   ← normative protocol (RFC-style, §1–17)
│   ├── schemas/                  ← JSON Schema for every wire structure
│   └── examples/                 ← L1–L5 wire-level examples
├── docs/
│   ├── why-sbp.md                ← Northbound vs Southbound essay
│   ├── getting-started.md        ← 5-minute quickstart
│   ├── concepts/
│   │   ├── tether.md
│   │   ├── resume.md
│   │   ├── roaming.md
│   │   ├── surfaces.md
│   │   ├── mcp-bridge.md
│   │   ├── lineage.md
│   │   └── federation.md         ← Silk Road / Independent Cities model (new)
│   └── reference/
│       ├── http-api.md
│       ├── websocket-frames.md
│       ├── error-codes.md
│       └── conformance-levels.md ← L1–L7 normative checklists (updated)
├── reference/
│   ├── server-python/
│   │   └── sbp_server/
│   │       └── backends/
│   │           ├── base.py       ← TetherBackend protocol (4 methods)
│   │           ├── memory.py     ← in-process default (dev/test)
│   │           ├── sqlite.py     ← SQLite + WAL mode (zero deps, new)
│   │           └── postgres.py   ← PostgreSQL + Redis pub/sub (new)
│   └── client-typescript/        ← SBPClient browser/Node library
├── conformance/                  ← language-agnostic test fixtures L1–L5
└── .github/                      ← CI: schema validation, conformance, Pages
```

## Documentation

- **Spec** — [`spec/SPEC.md`](spec/SPEC.md) (normative, RFC-style, §1–17)
- **Why SBP?** — [`docs/why-sbp.md`](docs/why-sbp.md) (the Northbound essay)
- **Getting started** — [`docs/getting-started.md`](docs/getting-started.md)
- **Concepts** — [Tether](docs/concepts/tether.md) · [Resume](docs/concepts/resume.md) · [Roaming](docs/concepts/roaming.md) · [Surfaces](docs/concepts/surfaces.md) · [MCP Bridge](docs/concepts/mcp-bridge.md) · [Lineage](docs/concepts/lineage.md) · [**Federation**](docs/concepts/federation.md)
- **Reference** — [HTTP API](docs/reference/http-api.md) · [WebSocket Frames](docs/reference/websocket-frames.md) · [Error Codes](docs/reference/error-codes.md) · [Conformance Levels](docs/reference/conformance-levels.md)
- **Implementations** — [`docs/implementations.md`](docs/implementations.md)

## Governance & contributing

- [`GOVERNANCE.md`](GOVERNANCE.md) — how decisions are made, the spec change process
- [`CONTRIBUTING.md`](CONTRIBUTING.md) — pull request workflow, RFC flow for breaking changes
- [`SECURITY.md`](SECURITY.md) — vulnerability disclosure
- [`CODE_OF_CONDUCT.md`](CODE_OF_CONDUCT.md) — Contributor Covenant

## License

Apache License 2.0 — see [`LICENSE`](LICENSE).

The spec, reference server, reference client, and conformance suite are all
Apache-2.0. You may build commercial products on SBP without obligation.
