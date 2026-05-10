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
and a bidirectional MCP bridge.

## Northbound vs Southbound — SBP and MCP are complementary

```
                   ┌───────────────────────┐
                   │  Apple Watch / Phone  │
                   │  Browser / Voice / …  │
                   └──────────┬────────────┘
                              │
                       ⇅  SBP (Northbound)
                              │
                   ┌──────────┴────────────┐
                   │   Agent Gateway       │
                   │   (Tether · Roaming · │
                   │    Surfaces · MCP-Br) │
                   └──────────┬────────────┘
                              │
                       ⇅  MCP (Southbound)
                              │
                   ┌──────────┴────────────┐
                   │  Databases · APIs     │
                   │  Files · Tools · Web  │
                   └───────────────────────┘
```

|                   | **MCP** (Southbound)                | **SBP** (Northbound)                       |
| ----------------- | ----------------------------------- | ------------------------------------------ |
| Connects agent to | Tools, databases, APIs              | Humans, devices, surfaces                  |
| Stateful?         | No (per-call)                       | **Yes** (sessions survive disconnects)     |
| Scope             | "Give the agent hands"              | "Give the agent a soul that persists"      |
| Typical transport | stdio, HTTP+SSE                     | HTTP + WebSocket                           |
| Transport runtime | Lightweight, ~50 LoC                | Stateful, durable backend required         |
| LLM-agnostic?     | Yes                                 | **Yes** — any OpenAI-compatible model      |
| Server-agnostic?  | Yes (stdio, HTTP)                   | **Yes** — swap backend implementations freely |
| Created by        | Anthropic                           | The State Bridge community (open standard) |

**SBP carries MCP, it does not replace it.** A surface (phone, watch) can declare
its own MCP tools (camera, GPS, contacts) at attach-time, and the agent can
invoke them through SBP's bidirectional bridge. *MCP gives the agent hands;
SBP gives the agent a soul that survives the drive home.*

## Model-agnostic. Server-agnostic. Your stack, your model.

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
  │                    SBP Server Backend                          │
  │  TetherQueue: in-memory     ← default (single-process dev)    │
  │  TetherQueue: Redis         ← multi-replica deployment        │
  │  TetherQueue: Temporal      ← enterprise durable execution     │
  │  TetherQueue: your-own      ← implement the 3-method protocol │
  └────────────────────────────────────────────────────────────────┘
```

**Why this matters:**
- A hospital can run SBP with a local Llama model on-premises — no cloud calls,
  no data leaving the building.
- A startup can switch from GPT-4o to Claude Sonnet mid-session by changing one
  field in the request — sessions survive the model swap.
- An enterprise can replace their queue backend from Redis to Temporal (or
  vice-versa) without changing a line of their application code.
- No vendor can "own" SBP by locking in an LLM or an infra tier. The protocol
  is defined by the wire format, not the model or the backend.

SBP is intentionally structured so that:
- **LLM selection** lives entirely in the `model` field of the request — any
  OpenAI-compatible model string is valid.
- **Backend selection** is encapsulated behind four small interfaces
  (`SessionStore`, `TetherQueue`, `SnapshotStore`, `RoamingTokenStore`). Swap
  them without changing your application or your surfaces.
- The spec defines **contracts** (what MUST happen), never **implementations**
  (how to build it).

## The five capabilities

| # | Capability        | What it does                                                        |
|---|-------------------|---------------------------------------------------------------------|
| 1 | **Tether**        | Server keeps producing turns even when no surface is attached       |
| 2 | **Resume**        | Same client reconnects after a disconnect; missed turns are drained |
| 3 | **Roaming**       | Export full session state → portable signed token → import anywhere |
| 4 | **Surface**       | Surfaces declare device type, screen size, capabilities at attach   |
| 5 | **MCP Bridge**    | Surfaces expose local MCP tools the agent can call over WebSocket   |

## Conformance levels

Pick how deep you implement. The reference server implements all five.

| Level | Adds                        | Effort           |
|-------|-----------------------------|------------------|
| **L1** | Stateful Proxy (`sbp` namespace on OpenAI completions) | An afternoon     |
| **L2** | + Tether + Resume           | A week           |
| **L3** | + Roaming (export/import/handoff/fork/lineage) | Two weeks        |
| **L4** | + Surface negotiation       | Days on top of L3 |
| **L5** | + MCP Bridge (full Northbound MCP) | A week on top of L4 |

See [`docs/reference/conformance-levels.md`](docs/reference/conformance-levels.md)
for the full normative checklists.

## Quickstart

Install the reference server, start it, and resume a session through a killed
WebSocket — all in five minutes.

```bash
# 1. Install + start the L5-conformant reference server (in-memory backend)
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
| Reference server | L5, in-memory backend (single-process; restart loses state) | L5, **Temporal backend** — durable Tether across pod restarts, scaling events, 30-day disconnects with guaranteed delivery |
| Surface translation | Frame protocol only (`TURN_CHUNK` descriptor) | **Contextual Translation Pipeline** — Gemini-Flash streaming adaptation (4k-token report → 2-sentence watch glance) |
| Surface MCP bridge | Wire protocol (`TOOL_CALL`/`TOOL_RESULT` frames, Future rendezvous) | **LLM-side connector** — dynamic injection of surface-declared tools into the LLM's `tool_calls`; per-tool authz |
| Memory | Bundle envelope + `schema_id` URI registry | `silkbridge.memory.v1` — episodic / semantic / procedural consolidation |
| Observability | None (logs to stdout) | Braintrust + LangSmith tracing, cost MVs, forensic trees |
| HITL | None | Full approval workflow with reviewer routing |
| Multi-tenancy | None | Sovereign VPC isolation |
| Operations | You run it | **SilkBridge Cloud** *(coming soon)* — managed, SLA-backed |

The protocol is free; the operational trust is what SilkBridge sells. Any
implementer can build an L5 server from this spec — but you'd be building
Twilio's stack from scratch.

## Repository map

```
statebridge-protocol/sbp/
├── spec/             ← the normative protocol (SPEC.md + JSON Schemas + examples)
├── docs/             ← GitHub Pages site (dev-friendly companion guide)
├── reference/
│   ├── server-python/    ← Apache-2.0 L5-conformant FastAPI server
│   └── client-typescript/← Apache-2.0 browser/Node client
├── conformance/      ← Language-agnostic test fixtures organized by L1–L5
└── .github/          ← CI: schema validation, conformance self-test, Pages deploy
```

## Documentation

- **Spec** — [`spec/SPEC.md`](spec/SPEC.md) (normative, RFC-style)
- **Why SBP?** — [`docs/why-sbp.md`](docs/why-sbp.md) (the Northbound essay)
- **Getting started** — [`docs/getting-started.md`](docs/getting-started.md)
- **Concepts** — [Tether](docs/concepts/tether.md) · [Resume](docs/concepts/resume.md) · [Roaming](docs/concepts/roaming.md) · [Surfaces](docs/concepts/surfaces.md) · [MCP Bridge](docs/concepts/mcp-bridge.md) · [Lineage](docs/concepts/lineage.md)
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
