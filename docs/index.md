---
title: State Bridge Protocol (SBP)
layout: default
---

# State Bridge Protocol (SBP)

> **The Northbound protocol for AI agents — durable state across disconnects, devices, and time.**
>
> Model-agnostic. Server-agnostic. Any LLM. Any backend. Your infrastructure, your rules.

[![Spec v1.2](https://img.shields.io/badge/spec-v1.2-blue.svg)](/spec/SPEC.md)
[![License: Apache 2.0](https://img.shields.io/badge/license-Apache--2.0-green.svg)](/LICENSE)

---

## The problem in one sentence

AI agents die when the WebSocket dies — and today, every agent platform
reinvents a private, incompatible, non-portable solution for keeping them alive.

**SBP is the open standard that fixes this.**

---

## What SBP does

```
[User's Apple Watch]  ←── SBP ──→  [Agent Gateway]  ←── MCP ──→  [Enterprise DB]
[User's iPhone]
[User's Laptop]
[AirPods / Voice]
```

When the user's device goes offline, SBP keeps the agent working and **buffers
its output** until the device comes back. When the user switches devices, SBP
**roams the full session state** — conversation history, memory, context — to
the new device. When the task should be passed to a specialist agent, SBP
**hands off** with a bridge message and full context.

---

## Model-agnostic. Server-agnostic.

SBP never locks your institution into a particular LLM or infrastructure stack.

| What you own | How SBP respects it |
|---|---|
| **Your LLM choice** | The `model` field accepts any OpenAI-compatible string. Run Claude, GPT-4o, Llama, DeepSeek, or your own fine-tuned model. Switch anytime — sessions survive model changes. |
| **Your backend** | Session storage, queue, snapshot store, and token store are all pluggable backend interfaces. PostgreSQL, DynamoDB, Redis, Temporal, SQLite — your choice. |
| **Your infrastructure** | Deploy on-premises, on any cloud, air-gapped, or in a sovereign VPC. No SBP feature requires a third-party service. |
| **Your data** | Nothing in the spec requires data to leave your network. The reference server's in-memory backend runs with zero external dependencies. |

---

## Five capabilities, five conformance levels

Pick how much you implement. Build L1 in an afternoon; reach L5 in a week.

| Level | Adds | Use case |
|---|---|---|
| **L1** — Stateful Proxy | `sbp` namespace on `/v1/chat/completions` | Drop-in session tracking for any OpenAI client |
| **L2** — Tether + Resume | Durable queue; survive disconnects | Mobile apps, spotty connectivity |
| **L3** — Roaming | Export / import / handoff / fork / lineage | Multi-device, multi-agent, multi-deployment |
| **L4** — Surface | Device capability declaration | Watch, phone, desktop, voice adaptation |
| **L5** — MCP Bridge | Bidirectional surface MCP tools | Camera, GPS, contacts callable by the agent |

---

## SBP and MCP — complementary, not competing

MCP gives agents **hands** to touch the machine world (databases, APIs, files).
SBP gives agents a **soul** that persists across space and time.

They compose:

```
Surface  ←(SBP Northbound)→  Gateway  ←(MCP Southbound)→  Tools
```

When a surface declares MCP tools at attach-time (e.g. `mcp_tools: ["camera", "gps"]`),
the SBP gateway becomes a bidirectional MCP bridge. The agent calls the
camera tool; the TOOL_CALL frame arrives at the surface; the photo comes back
as a TOOL_RESULT. MCP handles tool semantics; SBP handles the transport.

---

## Get started

- [**Getting started**](getting-started.md) — run a local L5 server and attach
  your first surface in 5 minutes.
- [**Why SBP?**](why-sbp.md) — the Northbound vs Southbound essay.
- [**Spec**](../spec/SPEC.md) — the full normative protocol document.
- [**Conformance levels**](reference/conformance-levels.md) — what each level
  requires, with checklists.

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
