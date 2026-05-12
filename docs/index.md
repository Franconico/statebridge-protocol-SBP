---
title: State Bridge Protocol (SBP)
layout: default
---

# State Bridge Protocol (SBP)

> **Give your AI agent a soul that persists.**  
> Across disconnects. Across devices. Across time.

Your user starts a complex research session on their laptop. They walk out the
door and pick it up on their phone — mid-sentence. The agent is still there,
thinking. They glance at their Apple Watch for a two-line summary on the train.
They hand the task to a specialist agent overnight. Back at the desktop in the
morning, the full context is waiting.

**On every surface, in every context, the agent remembers exactly where it left off.**

```
[Apple Watch]  ─┐
[iPhone]       ─┤
[Laptop]       ─┼── SBP ──→ [Agent Gateway] ──── MCP ───→ [Databases · APIs · Tools]
[AirPods/Voice]─┤
[Browser]      ─┘
```

That's what SBP does. It is the open standard for the *state layer* between an
AI agent and the human it serves — durable sessions, seamless device roaming,
surface-aware output, and a bidirectional MCP bridge.

[![Spec v1.2](https://img.shields.io/badge/spec-v1.2-blue.svg)](/spec/SPEC.md)
[![License: Apache 2.0](https://img.shields.io/badge/license-Apache--2.0-green.svg)](/LICENSE)

---

## The problem

AI agents die when the WebSocket dies — and today, every agent platform
reinvents a private, incompatible, non-portable solution for keeping them alive.

**SBP is the open standard that fixes this.**

---

## MCP gives agents hands. SBP gives agents a soul.

MCP connects agents to the machine world — databases, APIs, files. SBP connects
agents to the human world — and ensures they never forget who they were talking
to, what they were working on, or where they left off.

They compose:

```
Surface  ←(SBP Northbound)→  Gateway  ←(MCP Southbound)→  Tools
```

When a surface declares MCP tools at attach-time (e.g. `mcp_tools: ["camera", "gps"]`),
the SBP gateway becomes a bidirectional MCP bridge. The agent calls the camera
tool; the TOOL_CALL frame arrives at the surface; the photo comes back as a
TOOL_RESULT. MCP handles tool semantics; SBP handles the transport, the
buffering, and the roaming across devices.

| | **MCP** (Southbound) | **SBP** (Northbound) |
|---|---|---|
| Connects agent to | Tools, databases, APIs | Humans, devices, surfaces |
| Stateful? | No (per-call) | **Yes** — sessions survive disconnects |
| Core metaphor | "Give the agent hands" | "Give the agent a soul that persists" |

---

## Model-agnostic. Server-agnostic.

SBP never locks your institution into a particular LLM or infrastructure stack.

| What you own | How SBP respects it |
|---|---|
| **Your LLM choice** | The `model` field accepts any OpenAI-compatible string. Run Claude, GPT-4o, Llama, DeepSeek, or your own fine-tuned model. Switch anytime — sessions survive model changes. |
| **Your backend** | Session storage and tether queue are pluggable 4-method interfaces. SQLite (zero deps), PostgreSQL+Redis, Temporal, Cloudflare DO — your choice. |
| **Your infrastructure** | Deploy on-premises, on any cloud, air-gapped, or in a sovereign VPC. No SBP feature requires a third-party service. |
| **Your data** | Nothing in the spec requires data to leave your network. The SQLite backend runs with zero external dependencies. |

---

## Six capabilities, six conformance levels

Pick how much you implement. Build L1 in an afternoon; reach L6 in a few weeks.

| Level | Adds | Use case |
|---|---|---|
| **L1** — Stateful Proxy | `sbp` namespace on `/v1/chat/completions` | Drop-in session tracking for any OpenAI client |
| **L2** — Tether + Resume | Durable queue; survive disconnects | Mobile apps, spotty connectivity |
| **L3** — Roaming | Export / import / handoff / fork / lineage | Multi-device, multi-agent, multi-deployment |
| **L4** — Surface | Device capability declaration | Watch, phone, desktop, voice adaptation |
| **L5** — MCP Bridge | Bidirectional surface MCP tools | Camera, GPS, contacts callable by the agent |
| **L6** — Federation | `/.well-known/sbp`; cross-gateway bundle resolution by CID | No single point of failure; geographic distribution |

---

## Get started

- [**Getting started**](getting-started.md) — run a local server, kill the connection, watch The Tether drain.
- [**Why SBP?**](why-sbp.md) — the Northbound vs Southbound essay.
- [**Spec**](../spec/SPEC.md) — the full normative protocol document.
- [**Conformance levels**](reference/conformance-levels.md) — what each level requires, with checklists.

---

## Reference

| Resource | Link |
|---|---|
| Normative spec | [spec/SPEC.md](../spec/SPEC.md) |
| Reference Python server | [reference/server-python/](../reference/server-python/) |
| Reference TypeScript client | [reference/client-typescript/](../reference/client-typescript/) |
| JSON Schemas | [spec/schemas/](../spec/schemas/) |
| Wire examples | [spec/examples/](../spec/examples/) |
| Conformance suite | [conformance/](../conformance/) |
| Known implementations | [implementations.md](implementations.md) |
