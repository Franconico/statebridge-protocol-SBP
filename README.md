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

| Level | Name | Adds |
|-------|------|------|
| **L1** | Stateful Proxy | `sbp` namespace on OpenAI-compatible completions |
| **L2** | Tether + Resume | Durable turn queue; WebSocket attach/drain |
| **L3** | Roaming | Export/import/handoff/fork/lineage; content-addressed bundles |
| **L4** | Surface Negotiation | `SurfaceContext` at attach; device-aware output |
| **L5** | MCP Bridge | Bidirectional `TOOL_CALL`/`TOOL_RESULT` over WebSocket |
| **L6** | Gateway Federation | `/.well-known/sbp` discovery; cross-gateway bundle resolution by SHA-256 CID |

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

## Quickstart

**Prerequisites:** Python 3.10+, and one of:
- **Ollama** (free, local) — [install](https://ollama.com/download), then `ollama pull llama3.2`
- **Any OpenAI-compatible API key** (Groq, OpenAI, Together, etc.)

---

### ⚡ One-command demo

The fastest way to see SBP in action. Runs the full four-device cascade in a single interactive session:

```
💻 Laptop  →  agent streams a reply, WiFi drops mid-answer
📱 Phone   →  reconnects, recovers the full buffered response
⌚ Watch   →  agent distils the answer to a 2-sentence summary
🎧 Earbuds →  a voice-friendly version is spoken aloud through your speakers
```

**Step 1 — Install**

```bash
git clone https://github.com/Franconico/statebridge-protocol-SBP.git
cd statebridge-protocol-SBP/reference/server-python
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
```

**Step 2 — Configure your LLM** (the only two lines you need to change)

```bash
export SBP_LLM_BASE_URL=https://api.groq.com/openai/v1
export SBP_LLM_API_KEY=<your-key>
```

```bash
export SBP_MODEL=llama-3.3-70b-versatile
export SBP_JWT_SECRET=my-dev-secret-at-least-32-chars-long
```

> **Ollama instead?** `SBP_LLM_BASE_URL=http://localhost:11434/v1`, `SBP_LLM_API_KEY=ollama`, `SBP_MODEL=llama3.2`

**Step 3 — Start the server and run the demo**

```bash
sbp-server start --port 8080 &
sleep 2
sbp-demo
```

Type your question when prompted. The rest happens automatically — drop, recovery, watch summary, and audio.

> Audio uses the native TTS on every platform: `say` on macOS, `spd-say`/`espeak` on Linux, PowerShell `System.Speech` on Windows. No extra dependencies.

---

### 🛠 Dev-oriented demo — step by step

Want to see exactly what's happening on the wire? This walkthrough drives each stage manually so you can inspect every frame.

**Step 1 — Install** *(same as above, skip if done)*

```bash
git clone https://github.com/Franconico/statebridge-protocol-SBP.git
cd statebridge-protocol-SBP/reference/server-python
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
```

**Step 2 — Configure**

```bash
export SBP_LLM_BASE_URL=https://api.groq.com/openai/v1
export SBP_LLM_API_KEY=<your-key>
export SBP_MODEL=llama-3.3-70b-versatile
export SBP_JWT_SECRET=my-dev-secret-at-least-32-chars-long
```

**Step 3 — Start the server**

```bash
lsof -ti:8080 | xargs kill -9 2>/dev/null; true
sbp-server start --port 8080 &
sleep 2
```

**Step 4 — Create a session**

```bash
RESULT=$(curl -s -X POST http://localhost:8080/v1/chat/completions \
  -H "Content-Type: application/json" \
  -d "{\"model\":\"${SBP_MODEL}\",
       \"messages\":[{\"role\":\"user\",\"content\":\"Hello, starting a new session.\"}],
       \"sbp\":{}}")

export SID=$(echo "$RESULT" | python3 -c "import sys,json; d=json.loads(sys.stdin.read(),strict=False); print(d['sbp']['session_id'])")
export TOK=$(echo "$RESULT" | python3 -c "import sys,json; d=json.loads(sys.stdin.read(),strict=False); print(d['sbp']['session_token'])")
echo "Session: $SID  Token: $TOK"
```

You should see two UUIDs. If blank, run `echo $RESULT` to check for an error.

**Step 5 — Write the surface client**

A small WebSocket client that streams the agent's reply in colour:

```bash
cat > /tmp/sbp_ws_client.py << 'PYEOF'
import asyncio, websockets, json, os

CYAN = "\033[36m"; GREEN = "\033[32m"; RED = "\033[31m"
BOLD = "\033[1m";  RESET = "\033[0m"

async def run():
    sid        = os.environ["SID"]
    tok        = os.environ["TOK"]
    dev        = os.environ.get("SBP_DEV", "desktop")
    idle       = float(os.environ.get("SBP_IDLE", "0")) or None
    char_limit = int(os.environ.get("SBP_CHAR_LIMIT", "0")) or None
    uri        = f"ws://localhost:8080/v1/sbp/ws/{sid}"
    attach     = json.dumps({
        "type": "ATTACH_SESSION", "session_id": sid,
        "session_token": tok, "surface_context": {"device_type": dev},
    })
    chars_shown = 0
    first_chunk = True
    async with websockets.connect(uri) as ws:
        await ws.send(attach)
        while True:
            try:
                frame_str = await (asyncio.wait_for(ws.recv(), idle) if idle else ws.recv())
                frame     = json.loads(frame_str)
                ftype     = frame.get("type", "")
                if ftype == "SESSION_ATTACHED" and dev == "mobile":
                    queued = frame.get("queued_turns", 0)
                    print(f"\n{GREEN}✅  Reconnected on mobile{RESET}", flush=True)
                    if queued:
                        print(f"{GREEN}📬  Recovering {queued} buffered turn(s)...{RESET}\n", flush=True)
                elif ftype == "TURN_CHUNK":
                    content = frame.get("content", "")
                    if first_chunk:
                        print(f"\n{BOLD}Agent:{RESET} ", end="", flush=True)
                        first_chunk = False
                    print(f"{CYAN}{content}{RESET}", end="", flush=True)
                    chars_shown += len(content)
                    if char_limit and chars_shown >= char_limit:
                        print(f"\n\n{RED}📶  WiFi connection lost...{RESET}\n", flush=True)
                        break
                elif ftype == "TETHER_TURN" and dev == "mobile":
                    print(f"{CYAN}{frame.get('content', '')}{RESET}", flush=True)
                elif ftype == "TURN_COMPLETE":
                    print("", flush=True)
                    break
            except (asyncio.TimeoutError, websockets.exceptions.ConnectionClosed):
                break

asyncio.run(run())
PYEOF
```

**Step 6 — Ask a question, watch the drop**

```bash
printf "You: "
read -r USER_QUESTION
export Q="$USER_QUESTION"

PAYLOAD=$(python3 -c "
import json, os
q = os.environ['Q'] + ' Please answer in detail with several paragraphs.'
print(json.dumps({'model': os.environ['SBP_MODEL'], 'stream': True,
    'messages': [{'role': 'user', 'content': q}], 'sbp': {}}))")

SBP_DEV=desktop SBP_CHAR_LIMIT=25 python3 /tmp/sbp_ws_client.py &
WS_PID=$!
sleep 1
curl -s -X POST http://localhost:8080/v1/chat/completions \
  -H "Content-Type: application/json" -H "X-Session-Token: $TOK" \
  -d "$PAYLOAD" > /dev/null
wait $WS_PID
echo "[ Agent is still thinking in the background... ]"
sleep 8
```

**Step 7 — Reconnect as mobile, recover the full answer**

```bash
SBP_IDLE=15 SBP_DEV=mobile python3 /tmp/sbp_ws_client.py
```

**The agent kept thinking after the Wi-Fi dropped. That's The Tether.**

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
