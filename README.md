# State Bridge Protocol (SBP)

> **Give your AI agent a soul that persists.** Across netwrok disconnect, Across different HW devices (e.g. Laptop/Earbuds/Car/Smart watch/Phone). Across time.

You start a work session on your laptop. You walk out the
door and pick it up on your phone — mid-sentence. You get in the Car and roams to your car screen, the agent is still there,
thinking. You glance at your Smart Watch for a two-line summary while running, while getting feedback on your Earpods.
You hand the task to a specialist agent overnight. Back at the desktop in the
morning, the full context is waiting.

**On every surface, in every context, the agent maintains context where it left off.**

That's what SBP does. It is the open standard for the *state layer* between an
AI agent and the human it serves — durable sessions, seamless device roaming,
surface-aware output, and a bidirectional MCP bridge.

**Start in an afternoon. Runs entirely on your laptop. Zero dependencies beyond Python.**

```
  Your Laptop
  ┌──────────────────────────────────────────────┐
  │                                              │
  │   sbp-server start   (SQLite, no config)     │
  │         │                                    │
  │    ⇅ SBP (Northbound)                       │
  │         │                                    │
  │  Phone · Watch · Browser · Voice            │
  │                                              │
  │    ⇅ MCP (Southbound)                       │
  │         │                                    │
  │   Your tools, APIs, local files              │
  └──────────────────────────────────────────────┘
```

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

**SBP aims to fix this.** It is the open standard for the state layer between an agent
and the human it serves: durable sessions, device handoff, surface adaptation,
and a bidirectional MCP bridge.

---

## Quickstart — the 5-minute magic trick

The fastest way to understand SBP is to watch an agent survive a catastrophic disconnection.

**Prerequisites:** Python 3.10+, an OpenAI-compatible API key (any LLM), Node.js (for `wscat`).

```bash
# ── Step 1: Install and start the server ─────────────────────────────────────
pip install sbp-server-reference
export OPENAI_API_KEY=sk-...          # any OpenAI-compatible key
sbp-server start --port 8080 &
sleep 2

# ── Step 2: Start a long session — auto-capture the credentials ───────────────
RESULT=$(curl -s -X POST http://localhost:8080/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d '{"model":"gpt-4o",
       "messages":[{"role":"user","content":"Write a thorough history of the Roman Empire, section by section. Take your time."}],
       "sbp":{"checkpoint_every":1}}')

SID=$(echo "$RESULT" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d['sbp']['session_id'])")
TOK=$(echo "$RESULT" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d['sbp']['session_token'])")
echo "Session: $SID"

# ── Step 3: Attach a surface — then press Ctrl+C while the agent is mid-thought
npm install -g wscat 2>/dev/null      # one-time install
wscat -c "ws://localhost:8080/v1/sbp/ws/$SID" \
  --execute "{\"type\":\"ATTACH_SESSION\",\"session_id\":\"$SID\",\"session_token\":\"$TOK\",\"surface_context\":{\"device_type\":\"desktop\"}}"
# ↑ The agent starts streaming. Press Ctrl+C anywhere mid-response.
#   This simulates the user's Wi-Fi dropping, the browser closing, anything.

# ── Step 4: Reconnect — every missed turn drains through instantly ────────────
wscat -c "ws://localhost:8080/v1/sbp/ws/$SID" \
  --execute "{\"type\":\"ATTACH_SESSION\",\"session_id\":\"$SID\",\"session_token\":\"$TOK\",\"surface_context\":{\"device_type\":\"mobile\"}}"
# The agent is still mid-thought. Nothing was lost.
# Notice: surface_context changed from "desktop" to "mobile" — same session, new device.
```

**The agent's consciousness survived the drive home. That's The Tether.**

Full walkthrough with multi-device roaming and MCP tools: [`docs/getting-started.md`](docs/getting-started.md).

---

## SBP and MCP — complementary, not competing

MCP gives agents **hands** to touch the machine world (databases, APIs, files).
SBP gives agents a **soul** that persists across space and time.

```
Surface  ←(SBP Northbound)→  Gateway  ←(MCP Southbound)→  Tools
```

|                   | **MCP** (Southbound)                | **SBP** (Northbound)                       |
| ----------------- | ----------------------------------- | ------------------------------------------ |
| Connects agent to | Tools, databases, APIs              | Humans, devices, surfaces                  |
| Stateful?         | No (per-call)                       | **Yes** (sessions survive disconnects)     |
| Scope             | "Give the agent hands"              | "Give the agent a soul that persists"      |
| Typical transport | stdio, HTTP+SSE                     | HTTP + WebSocket                           |
| LLM-agnostic?     | Yes                                 | **Yes** — any OpenAI-compatible model      |
| Server-agnostic?  | Yes                                 | **Yes** — swap backend implementations freely |
| Created by        | Anthropic                           | The State Bridge community (open standard) |

**SBP carries MCP — it does not replace it.** A surface (phone, watch) can
declare its own MCP tools (camera, GPS, contacts) at attach-time, and the agent
can invoke them through SBP's bidirectional bridge. MCP handles tool semantics;
SBP handles the transport, the buffering, and the device roaming.

---

## The six capabilities

| # | Capability     | What it does                                                         |
|---|----------------|----------------------------------------------------------------------|
| 1 | **Tether**     | Server keeps producing turns even when no surface is attached        |
| 2 | **Resume**     | Same client reconnects after a disconnect; missed turns are drained  |
| 3 | **Roaming**    | Export full session state → portable signed token → import anywhere  |
| 4 | **Surface**    | Surfaces declare device type, screen size, capabilities at attach    |
| 5 | **MCP Bridge** | Surfaces expose local MCP tools the agent can call over WebSocket    |
| 6 | **Federation** | Independent gateways discover each other and exchange bundles by CID |

---

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

See [`docs/reference/conformance-levels.md`](docs/reference/conformance-levels.md) for normative checklists.

---

## Model-agnostic. Server-agnostic.

SBP places **no requirements** on which LLM or infrastructure you use:

- A hospital can run SBP with a local Llama model on-premises — no cloud calls,
  no data leaving the building.
- A startup can switch from GPT-4o to Claude mid-session by changing one field —
  sessions survive the model swap.
- An enterprise can move from SQLite to PostgreSQL to Temporal without changing
  application code or surface clients.

The `model` field accepts any OpenAI-compatible string. The backend is a
4-method protocol interface — SQLite, PostgreSQL+Redis, Temporal, Cloudflare DO,
or your own implementation.

---

## Scaling to production

Once you've experienced the magic locally, the same protocol scales without
changing a line of application code:

```
  Single laptop (L1–L5)              Production (L5–L6)
  ┌─────────────────────┐            ┌──────────────┐  ┌──────────────┐  ┌──────────────┐
  │  sbp-server         │            │ Gateway NYC  │  │ Gateway FRA  │  │ Gateway SIN  │
  │  SQLite backend     │   ──────▶  │ PostgreSQL   │  │ PostgreSQL   │  │ PostgreSQL   │
  │  your laptop        │            │ + Redis      │  │ + Redis      │  │ + Redis      │
  └─────────────────────┘            └──────┬───────┘  └──────┬───────┘  └──────┬───────┘
                                            └─────── L6 Federation ──────────────┘
```

Backend options — swap without touching surface clients:

| Backend | Best for |
|---|---|
| `memory.py` | Unit tests, CI |
| `sqlite.py` | Local dev, single-node production |
| `postgres.py` | Multi-replica, PostgreSQL + Redis pub/sub |
| Temporal *(SilkBridge)* | 30-day disconnects, guaranteed delivery across pod restarts |

---

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
│   │   └── federation.md         ← Silk Road / Independent Cities model
│   └── reference/
│       ├── http-api.md
│       ├── websocket-frames.md
│       ├── error-codes.md
│       └── conformance-levels.md ← L1–L7 normative checklists
├── reference/
│   ├── server-python/
│   │   └── sbp_server/
│   │       └── backends/
│   │           ├── base.py       ← TetherBackend protocol (4 methods)
│   │           ├── memory.py     ← in-process default (dev/test)
│   │           ├── sqlite.py     ← SQLite + WAL mode (zero deps)
│   │           └── postgres.py   ← PostgreSQL + Redis pub/sub
│   └── client-typescript/        ← SBPClient browser/Node library
├── conformance/                  ← language-agnostic test fixtures L1–L5
└── .github/                      ← CI: schema validation, conformance, Pages
```

---

## Documentation

- **Spec** — [`spec/SPEC.md`](spec/SPEC.md) (normative, RFC-style, §1–17)
- **Why SBP?** — [`docs/why-sbp.md`](docs/why-sbp.md)
- **Getting started** — [`docs/getting-started.md`](docs/getting-started.md)
- **Concepts** — [Tether](docs/concepts/tether.md) · [Resume](docs/concepts/resume.md) · [Roaming](docs/concepts/roaming.md) · [Surfaces](docs/concepts/surfaces.md) · [MCP Bridge](docs/concepts/mcp-bridge.md) · [Lineage](docs/concepts/lineage.md) · [Federation](docs/concepts/federation.md)
- **Reference** — [HTTP API](docs/reference/http-api.md) · [WebSocket Frames](docs/reference/websocket-frames.md) · [Error Codes](docs/reference/error-codes.md) · [Conformance Levels](docs/reference/conformance-levels.md)
- **Implementations** — [`docs/implementations.md`](docs/implementations.md)

---

## Governance & contributing

- [`GOVERNANCE.md`](GOVERNANCE.md) — how decisions are made, the spec change process
- [`CONTRIBUTING.md`](CONTRIBUTING.md) — pull request workflow, RFC flow for breaking changes
- [`SECURITY.md`](SECURITY.md) — vulnerability disclosure
- [`CODE_OF_CONDUCT.md`](CODE_OF_CONDUCT.md) — Contributor Covenant

---

## License

Apache License 2.0 — see [`LICENSE`](LICENSE).

The spec, reference server, reference client, and conformance suite are all
Apache-2.0. You may build commercial products on SBP without obligation.

---

*Don't want to build and operate the backend yourself?*  
**[SilkBridge](https://silkbridge.io)** offers a production-grade hosted SBP service — durable Tether across pod restarts and 30-day disconnects, a Contextual Translation Pipeline for surface-adaptive output, and a managed gateway mesh. Point your agent at `api.silkbridge.cloud` and get L5 instantly. No servers to run.
